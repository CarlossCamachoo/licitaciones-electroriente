"""
Documentos de la empresa: catalogo, archivos subidos y cruce con las alertas.

Los archivos se guardan en docs/empresa/ (fuera de git) con nombre aleatorio.
El nombre original solo se guarda como texto para mostrarlo.
"""

import json
import os
import re
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

import yaml

import radar

DIR = radar.RAIZ / "docs" / "empresa"
INDICE = DIR / "indice.json"
MAX_BYTES = 25 * 1024 * 1024
DIAS_AVISO = 15

# Extension permitida -> primeros bytes que debe tener el archivo.
FIRMAS = {
    ".pdf": b"%PDF", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff", ".docx": b"PK\x03\x04", ".xlsx": b"PK\x03\x04",
}
TIPOS = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
ID_ARCHIVO = re.compile(r"^[0-9a-f]{32}$")

_candado = threading.Lock()


class ErrorDocumento(Exception):
    """Error pensado para mostrarse al usuario tal cual."""


def _texto(v):
    return " ".join(str(v or "").split())


def catalogo():
    with open(radar.RAIZ / "config" / "documentos.yaml", encoding="utf-8") as f:
        cats = (yaml.safe_load(f) or {}).get("categorias", [])
    return [{"id": _texto(c.get("id")),
             "titulo": _texto(c.get("titulo")),
             "descripcion": _texto(c.get("descripcion")),
             "documentos": [{
                 **{k: _texto(d.get(k)) for k in
                    ("id", "nombre", "para_que", "emite", "vigencia",
                     "cuando", "pendiente", "condicion")},
                 "si_menciona": [str(t) for t in d.get("si_menciona", [])],
             } for d in c.get("documentos", [])]}
            for c in cats]


def _leer_indice():
    try:
        with open(INDICE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return []


def _guardar_indice(entradas):
    tmp = INDICE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entradas, f, ensure_ascii=False, indent=1)
    os.replace(tmp, INDICE)


def estado_archivo(entrada, hoy=None):
    hoy = hoy or date.today()
    if not entrada.get("vence"):
        return "sin_fecha"
    dias = (date.fromisoformat(entrada["vence"]) - hoy).days
    if dias < 0:
        return "vencido"
    return "por_vencer" if dias <= DIAS_AVISO else "vigente"


def _publico(entrada):
    return {"id": entrada["id"], "original": entrada["original"],
            "subido": entrada["subido"], "vence": entrada["vence"],
            "bytes": entrada["bytes"], "estado": estado_archivo(entrada)}


def _estado_doc(archivos):
    """falta | listo | por_vencer | vencido, segun los archivos del documento."""
    if not archivos:
        return "falta"
    estados = {estado_archivo(a) for a in archivos}
    if estados & {"vigente", "sin_fecha"}:
        return "listo"
    return "por_vencer" if "por_vencer" in estados else "vencido"


def listar():
    """Catalogo con el estado de cada documento y sus archivos."""
    entradas = _leer_indice()
    cats = catalogo()
    for c in cats:
        for d in c["documentos"]:
            archivos = [e for e in entradas if e["doc"] == d["id"]]
            d["archivos"] = [_publico(a) for a in archivos]
            d["estado"] = _estado_doc(archivos)
    return cats


def guardar(doc_id, original, vence, contenido):
    if doc_id not in {d["id"] for c in catalogo() for d in c["documentos"]}:
        raise ErrorDocumento("Documento desconocido.")
    original = radar.limpiar(original)[:120] or "documento"
    ext = Path(original).suffix.lower()
    if ext not in FIRMAS:
        raise ErrorDocumento("Formato no permitido. Usa PDF, PNG, JPG, DOCX o XLSX.")
    if not contenido:
        raise ErrorDocumento("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise ErrorDocumento("El archivo supera 25 MB.")
    if not contenido.startswith(FIRMAS[ext]):
        raise ErrorDocumento("El contenido no corresponde a la extensión del archivo.")
    if vence:
        try:
            if not 2000 <= date.fromisoformat(vence).year <= 2100:
                raise ValueError
        except ValueError:
            raise ErrorDocumento("La fecha de vencimiento no es válida.")

    fid = uuid.uuid4().hex
    entrada = {"id": fid, "doc": doc_id, "original": original, "ext": ext,
               "bytes": len(contenido), "vence": vence or "",
               "subido": datetime.now().strftime("%Y-%m-%d %H:%M")}
    with _candado:
        DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        destino = DIR / (fid + ext)
        fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
        entradas = _leer_indice()
        entradas.append(entrada)
        _guardar_indice(entradas)
    return _publico(entrada)


def _buscar(fid):
    if not ID_ARCHIVO.match(fid or ""):
        raise ErrorDocumento("Archivo no encontrado.")
    for e in _leer_indice():
        if e["id"] == fid:
            return e
    raise ErrorDocumento("Archivo no encontrado.")


def eliminar(fid):
    with _candado:
        entrada = _buscar(fid)
        try:
            (DIR / (entrada["id"] + entrada["ext"])).unlink()
        except FileNotFoundError:
            pass
        _guardar_indice([e for e in _leer_indice() if e["id"] != fid])


def abrir(fid):
    """(bytes, tipo MIME, extension) de un archivo subido."""
    entrada = _buscar(fid)
    ruta = DIR / (entrada["id"] + entrada["ext"])
    try:
        return ruta.read_bytes(), TIPOS[entrada["ext"]], entrada["ext"]
    except FileNotFoundError:
        raise ErrorDocumento("Archivo no encontrado.")


def generales(cats=None):
    """Documentos que se piden en toda licitacion, con su estado."""
    cats = cats or listar()
    return [{"id": d["id"], "nombre": d["nombre"], "estado": d["estado"]}
            for c in cats for d in c["documentos"] if d["cuando"] == "siempre"]


def requisitos(resultado, cats=None):
    """Que documentos hacen falta para una alerta.

    Es una estimacion por reglas, no la lectura del pliego:
      necesarios: los que siempre se piden (y el acuerdo de consorcio si la
                  alerta requiere aliado)
      probables:  los que dependen del pliego pero el objeto sugiere que si
      verificar:  el resto de los que dependen del pliego
    """
    cats = cats or listar()
    texto = radar.normalizar(resultado.get("descripcion", ""))
    grupos = {"necesarios": [], "probables": [], "verificar": []}
    for c in cats:
        for d in c["documentos"]:
            item = {"id": d["id"], "nombre": d["nombre"], "estado": d["estado"],
                    "general": d["cuando"] == "siempre"}
            if d["cuando"] == "siempre":
                grupos["necesarios"].append(item)
            elif d["cuando"] == "si_aplica":
                if d["condicion"] == "requiere_aliado" and resultado.get("requiere_aliado"):
                    grupos["necesarios"].append(item)
            elif d["cuando"] == "segun_pliego":
                if any(radar.contiene(texto, t) for t in d["si_menciona"]):
                    grupos["probables"].append(item)
                else:
                    grupos["verificar"].append(item)
    return grupos
