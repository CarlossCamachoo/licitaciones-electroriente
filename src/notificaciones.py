"""
Notificaciones: avisa cuando aparece una licitacion nueva de Santander.

El panel consulta SECOP solo cada 30 minutos (ver servidor.py). Cada vez, las
alertas de entidades de Santander que no se habian visto antes quedan guardadas
aqui hasta que se marquen como leidas. Se guarda en data/notificaciones.json
(fuera de git).

La primera vez no se avisa de lo que ya existe: se toma como punto de partida,
para no llenar la campana con decenas de procesos viejos.
"""

import json
import os
import threading
import time

import radar

RUTA = radar.RAIZ / "data" / "notificaciones.json"
DEPARTAMENTO = "Santander"
NIVELES = ("alta", "media")   # solo alertas; las senales debiles de "por revisar" no suenan
MAX_ITEMS = 100
MAX_VISTOS = 20000

_candado = threading.Lock()


def _leer():
    try:
        with open(RUTA, encoding="utf-8") as f:
            d = json.load(f)
        return {"vistos": list(d.get("vistos", [])), "items": list(d.get("items", [])),
                "iniciado": bool(d.get("iniciado"))}
    except (FileNotFoundError, ValueError):
        return {"vistos": [], "items": [], "iniciado": False}


def _guardar(d):
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    tmp = RUTA.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, RUTA)


def registrar(resultados):
    """Guarda como notificacion cada alerta de Santander que no se habia visto."""
    candidatas = [r for r in resultados
                  if r.get("departamento") == DEPARTAMENTO and r.get("nivel") in NIVELES and r.get("id")]
    with _candado:
        d = _leer()
        vistos = set(d["vistos"])
        nuevas = []
        for r in candidatas:
            if r["id"] in vistos:
                continue
            vistos.add(r["id"])
            if d["iniciado"]:
                nuevas.append({
                    "id": r["id"], "entidad": r["entidad"],
                    "descripcion": r["descripcion"][:240], "valor": r["valor_cop"],
                    "puntaje": r["puntaje"], "nivel": r["nivel"], "url": r["url"],
                    "publicado": r["fecha_publicacion"],
                    "detectado_ts": int(time.time()), "leida": False})
        d["iniciado"] = True
        d["items"] = (nuevas + d["items"])[:MAX_ITEMS]
        d["vistos"] = list(vistos)[-MAX_VISTOS:]
        _guardar(d)
        return len(nuevas)


def listar():
    with _candado:
        items = _leer()["items"]
    return {"items": items, "sin_leer": sum(1 for i in items if not i["leida"])}


def marcar_leidas():
    with _candado:
        d = _leer()
        for i in d["items"]:
            i["leida"] = True
        _guardar(d)
