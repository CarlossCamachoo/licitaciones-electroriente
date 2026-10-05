#!/usr/bin/env python3
"""
Publica la web compartida: una version estatica del panel, protegida con contrasena.

    CLAVE_WEB=... python src/publicar.py --destino sitio

El sitio publicado (GitHub Pages) es publico, pero los datos van cifrados: son archivos
`data/*.enc` (gzip + AES-256-GCM, clave derivada de la contrasena con PBKDF2) que el
navegador descifra al escribir la contrasena. Sin ella no se puede leer nada.
La contrasena nunca se guarda: llega por la variable de entorno CLAVE_WEB.

Que incluye: Radar, Por revisar, Oportunidades futuras, Mercado y Criterios.
Que NO incluye, a proposito: los archivos de la empresa (no deben quedar en un sitio publico)
ni la campana. De los documentos solo viaja su ESTADO (falta, cargado, vence pronto, vencido), a
partir del secreto ESTADO_DOCUMENTOS que sube el panel local (documentos.sincronizar_web). Si hay HOJA_URL y HOJA_TOKEN, lleva (cifrada) la direccion de la hoja
compartida del equipo, para copiar ahi los «Me interesa». Las decisiones "Me interesa / Descartar" se guardan en el
navegador de cada persona.

Cada ejecucion recalcula los periodos de 3 a 30 dias con una sola consulta a SECOP. Los de 60 y 90 dias
se quitaron (casi todo lo viejo es «regimen especial» sin fecha de cierre). Los contratos del
mercado se recalculan solo una vez al dia porque tardan mas.
"""

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import competencia
import documentos
import mercado
import radar
import servidor

ITERACIONES = 600000                # debe coincidir con web/estatico/shim.js
ACTIVOS = ["logo.webp", "favicon-32.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png"]


def derivar(contrasena, sal):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=ITERACIONES)
    return kdf.derive(contrasena.encode("utf-8"))


def cifrar(clave, obj):
    """gzip + AES-GCM. Formato: 12 bytes de nonce + texto cifrado con su etiqueta."""
    crudo = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    return nonce + AESGCM(clave).encrypt(nonce, gzip.compress(crudo, 9), None)


def descifrar(clave, datos):
    return json.loads(gzip.decompress(AESGCM(clave).decrypt(datos[:12], datos[12:], None)))


def normalizar_usuario(usuario):
    """Minusculas y sin tildes: «Ana» y «ana» son el mismo usuario. Debe coincidir con web/estatico/shim.js."""
    u = unicodedata.normalize("NFD", usuario.strip().lower())
    return "".join(c for c in u if unicodedata.category(c) != "Mn")


def id_ranura(usuario):
    return hashlib.sha256(("radar:" + normalizar_usuario(usuario)).encode("utf-8")).hexdigest()[:32]


def leer_usuarios(texto):
    """Lineas «usuario|Nombre|contrasena» (las vacias y las que empiezan por # se ignoran)."""
    usuarios = []
    for linea in (texto or "").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        partes = linea.split("|", 2)
        if len(partes) != 3:
            sys.exit("USUARIOS_WEB: cada linea debe ser usuario|Nombre|contrasena")
        usuario, nombre, contrasena = normalizar_usuario(partes[0]), partes[1].strip(), partes[2]
        if not re.fullmatch(r"[a-z0-9._-]{2,30}", usuario) or not nombre:
            sys.exit(f"USUARIOS_WEB: usuario o nombre no validos en «{partes[0][:20]}»")
        if len(contrasena) < 12:
            sys.exit(f"USUARIOS_WEB: la contrasena de «{usuario}» es muy corta (minimo 12 caracteres)")
        if usuario in [u[0] for u in usuarios]:
            sys.exit(f"USUARIOS_WEB: el usuario «{usuario}» esta repetido")
        usuarios.append((usuario, nombre, contrasena))
    return usuarios


def escribir_usuarios(datos_dir, usuarios, clave_datos):
    """Una «ranura» por persona: la clave de los datos, cifrada con la contrasena de esa persona.

    Quien entra con su usuario y contrasena abre su ranura, saca la clave de los datos y su nombre.
    Nadie recibe la contrasena maestra (CLAVE_WEB), y cambiarla re-cifra todo para quienes siguen."""
    ruta = datos_dir / "usuarios.json"
    if not usuarios:
        ruta.unlink(missing_ok=True)
        return
    k_b64 = base64.b64encode(clave_datos).decode()
    ranuras = {}
    for usuario, nombre, contrasena in usuarios:
        sal = os.urandom(16)
        ranuras[id_ranura(usuario)] = {
            "s": base64.b64encode(sal).decode(),
            "b": base64.b64encode(cifrar(derivar(contrasena, sal), {"n": nombre, "k": k_b64})).decode()}
    ruta.write_text(json.dumps(ranuras, separators=(",", ":")), encoding="utf-8")


def respuesta_alertas(dias, tabla_mercado, forzar=False):
    datos = servidor.calcular(dias, forzar=forzar)
    return {**datos, "mercado": mercado.estado(),
            "resultados": [
                {**r, "documentos": None,
                 "historial": mercado.historial_de(r["entidad"], tabla_mercado),
                 "renovacion": mercado.renovacion_de(r["entidad"], r["coincidencias"]),
                 "competencia": competencia.de_alerta(r["entidad"], r["coincidencias"])}
                for r in datos["resultados"]]}


def asegurar_mercado():
    """Mercado y competencia: se reconstruyen solo si estan vencidos (el cache de GitHub
    Actions conserva data/mercado.json y data/competencia.json entre ejecuciones)."""
    if not mercado._vigente(mercado.datos_listos()):
        print("[publicar] reconstruyendo mercado…", flush=True)
        mercado._memoria["datos"] = mercado._construir()
    if not competencia._vigente(competencia.datos_listos()):
        print("[publicar] reconstruyendo competencia…", flush=True)
        competencia._memoria["datos"] = competencia._construir()


def estado_documentos():
    """Resumen de documentos del secreto ESTADO_DOCUMENTOS, o None si no hay (la pestaña queda oculta)."""
    crudo = os.environ.get("ESTADO_DOCUMENTOS", "").strip()
    if not crudo:
        return None
    try:
        return documentos.resumen_valido(json.loads(crudo))
    except ValueError as e:
        sys.exit(f"ESTADO_DOCUMENTOS no es valido: {e}")


def armar_pagina(destino, con_documentos=False):
    """Copia web/index.html con las rutas relativas y la pantalla de acceso.

    La pestaña Documentos solo se muestra si hay estado de documentos que publicar."""
    web = radar.RAIZ / "web"
    html = (web / "index.html").read_text(encoding="utf-8")
    reemplazos = [
        ('<html lang="es">', '<html lang="es" data-estatico>'),
        ('href="/favicon.png"', 'href="favicon-32.png"'),
        ('href="/apple-touch-icon.png"', 'href="apple-touch-icon.png"'),
        ('href="/manifest.webmanifest"', 'href="manifest.webmanifest"'),
        ('src="/logo.webp"', 'src="logo.webp"'),
        ('<meta name="theme-color" content="#000775">',
         '<meta name="theme-color" content="#000775">\n<meta name="robots" content="noindex, nofollow">\n'
         '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; '
         "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
         "script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://script.google.com https://script.googleusercontent.com; "
         "base-uri 'none'; form-action 'none'\">"),
    ]
    if not con_documentos:
        reemplazos.append(('id="tab-docs" aria-selected="false" tabindex="-1" type="button"',
                           'id="tab-docs" aria-selected="false" tabindex="-1" type="button" hidden'))
    for viejo, nuevo in reemplazos:
        if viejo not in html:
            raise SystemExit(f"No se encontro en web/index.html: {viejo[:60]}")
        html = html.replace(viejo, nuevo, 1)
    estilos = (web / "estatico" / "login.css").read_text(encoding="utf-8")
    shim = (web / "estatico" / "shim.js").read_text(encoding="utf-8")
    login = (web / "estatico" / "login.html").read_text(encoding="utf-8")
    html = html.replace("</head>", f"<style>\n{estilos}</style>\n<script>\n{shim}</script>\n</head>", 1)
    html = html.replace("<body>", f"<body>\n{login}", 1)
    # Version de la pagina: la web revisa version.txt de vez en cuando y avisa si hay una nueva.
    version = hashlib.sha256(html.encode("utf-8")).hexdigest()[:12]
    html = html.replace('<meta charset="utf-8">', f'<meta charset="utf-8">\n<meta name="radar-version" content="{version}">', 1)
    (destino / "index.html").write_text(html, encoding="utf-8")
    (destino / "version.txt").write_text(version, encoding="utf-8")
    for nombre in ACTIVOS:
        shutil.copyfile(web / nombre, destino / nombre)
    manifiesto = json.loads((web / "manifest.webmanifest").read_text(encoding="utf-8"))
    manifiesto.update(start_url="./", scope="./")
    for icono in manifiesto["icons"]:
        icono["src"] = icono["src"].lstrip("/")
    (destino / "manifest.webmanifest").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1), encoding="utf-8")
    (destino / ".nojekyll").write_text("", encoding="utf-8")
    (destino / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Publica la web compartida (cifrada)")
    ap.add_argument("--destino", required=True, help="carpeta del sitio (el repositorio publico clonado)")
    ap.add_argument("--solo-pagina", action="store_true", help="no consulta SECOP: solo arma la pagina")
    args = ap.parse_args()
    contrasena = os.environ.get("CLAVE_WEB", "")
    if len(contrasena) < 12:
        sys.exit("CLAVE_WEB falta o es muy corta (minimo 12 caracteres): una contrasena corta se puede adivinar "
                 "porque los datos cifrados son publicos.")

    destino = Path(args.destino)
    datos_dir = destino / "data"
    datos_dir.mkdir(parents=True, exist_ok=True)

    sal_ruta = datos_dir / "salt.txt"
    if sal_ruta.exists():
        sal = base64.b64decode(sal_ruta.read_text().strip())
    else:
        sal = os.urandom(16)
        sal_ruta.write_text(base64.b64encode(sal).decode())
    clave = derivar(contrasena, sal)

    estado_docs = estado_documentos()
    armar_pagina(destino, con_documentos=estado_docs is not None)
    if estado_docs is None:
        (datos_dir / "documentos.enc").unlink(missing_ok=True)
    else:
        (datos_dir / "documentos.enc").write_bytes(cifrar(clave, documentos.listar_desde(estado_docs)))
    # check.enc deja comprobar la contrasena sin descargar nada pesado.
    (datos_dir / "check.enc").write_bytes(cifrar(clave, {"ok": True}))
    # Hoja compartida del equipo (autorizado por el dueño del proyecto): su direccion y clave viajan
    # cifradas con la contrasena, como todo lo demas. El script de la hoja solo acepta ids y enlaces
    # reales de SECOP y limita las filas por hora (app/hoja_equipo.gs).
    hoja_url, hoja_token = os.environ.get("HOJA_URL", ""), os.environ.get("HOJA_TOKEN", "")
    if hoja_url.startswith("https://script.google.com/") and hoja_token:
        (datos_dir / "hoja.enc").write_bytes(cifrar(clave, {"url": hoja_url, "token": hoja_token}))
    else:
        (datos_dir / "hoja.enc").unlink(missing_ok=True)
    escribir_usuarios(datos_dir, leer_usuarios(os.environ.get("USUARIOS_WEB", "")), clave)
    if args.solo_pagina:
        return

    manifiesto_ruta = datos_dir / "manifest.json"
    try:
        manifiesto = json.loads(manifiesto_ruta.read_text())
    except (FileNotFoundError, ValueError):
        manifiesto = {}
    ahora = int(time.time())

    t0 = time.time()
    asegurar_mercado()
    tabla = mercado.historial()

    # Una sola consulta a SECOP (30 dias); 3, 7 y 15 dias salen de ella sin volver a llamar.
    for d in (30,) + tuple(p for p in servidor.PERIODOS if p != 30):
        t = time.time()
        (datos_dir / f"alertas_{d}.enc").write_bytes(cifrar(clave, respuesta_alertas(d, tabla, forzar=(d == 30))))
        print(f"[publicar] alertas {d} dias: {time.time() - t:.0f} s", flush=True)
    for viejo in (60, 90):                    # periodos que ya no se ofrecen
        (datos_dir / f"alertas_{viejo}.enc").unlink(missing_ok=True)

    (datos_dir / "vencimientos.enc").write_bytes(cifrar(clave, {
        "estado": mercado.estado(), "contratos": mercado.vencimientos()}))
    (datos_dir / "mercado.enc").write_bytes(cifrar(clave, {
        "estado": mercado.estado(), "contratos": mercado.contratos_del_ano(),
        "competencia": competencia.para_mercado()}))
    (datos_dir / "criterios.enc").write_bytes(cifrar(clave, servidor.criterios()))

    manifiesto.update(actualizado_ts=ahora)
    manifiesto_ruta.write_text(json.dumps(manifiesto))
    print(f"[publicar] listo en {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
