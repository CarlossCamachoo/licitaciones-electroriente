#!/usr/bin/env python3
"""
Publica la web compartida: una version estatica del panel, protegida con contrasena.

    CLAVE_WEB=... python src/publicar.py --destino sitio

El sitio publicado (GitHub Pages) es publico, pero los datos van cifrados: son archivos
`data/*.enc` (gzip + AES-256-GCM, clave derivada de la contrasena con PBKDF2) que el
navegador descifra al escribir la contrasena. Sin ella no se puede leer nada.
La contrasena nunca se guarda: llega por la variable de entorno CLAVE_WEB.

Que incluye: Radar, Por revisar, Oportunidades futuras, Mercado y Criterios.
Que NO incluye, a proposito: los documentos de la empresa (no deben quedar en un sitio
publico) ni la campana. Las decisiones "Me interesa / Descartar" se guardan en el
navegador de cada persona.

Cada ejecucion recalcula los periodos de 3 a 30 dias. Los de 60 y 90 dias, y los
contratos del mercado, se recalculan solo una o dos veces al dia porque tardan mas.
"""

import argparse
import base64
import gzip
import json
import os
import shutil
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import competencia
import mercado
import radar
import servidor

ITERACIONES = 600000                # debe coincidir con web/estatico/shim.js
PERIODOS_RAPIDOS = (3, 7, 15, 30)
PERIODOS_PESADOS = (60, 90)
REFRESCO_PESADOS = 20 * 3600        # segundos
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


def respuesta_alertas(dias, tabla_mercado):
    datos = servidor.calcular(dias, forzar=True)
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


def armar_pagina(destino):
    """Copia web/index.html con las rutas relativas, la pantalla de acceso y sin documentos."""
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
         "script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
         "base-uri 'none'; form-action 'none'\">"),
        # La pestaña de documentos no existe en la web compartida.
        ('id="tab-docs" aria-selected="false" tabindex="-1" type="button"',
         'id="tab-docs" aria-selected="false" tabindex="-1" type="button" hidden'),
    ]
    for viejo, nuevo in reemplazos:
        if viejo not in html:
            raise SystemExit(f"No se encontro en web/index.html: {viejo[:60]}")
        html = html.replace(viejo, nuevo, 1)
    estilos = (web / "estatico" / "login.css").read_text(encoding="utf-8")
    shim = (web / "estatico" / "shim.js").read_text(encoding="utf-8")
    login = (web / "estatico" / "login.html").read_text(encoding="utf-8")
    html = html.replace("</head>", f"<style>\n{estilos}</style>\n<script>\n{shim}</script>\n</head>", 1)
    html = html.replace("<body>", f"<body>\n{login}", 1)
    (destino / "index.html").write_text(html, encoding="utf-8")
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

    armar_pagina(destino)
    # check.enc deja comprobar la contrasena sin descargar nada pesado.
    (datos_dir / "check.enc").write_bytes(cifrar(clave, {"ok": True}))
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

    periodos = list(PERIODOS_RAPIDOS)
    if ahora - manifiesto.get("pesados_ts", 0) > REFRESCO_PESADOS:
        periodos += PERIODOS_PESADOS
        manifiesto["pesados_ts"] = ahora
    for d in periodos:
        t = time.time()
        (datos_dir / f"alertas_{d}.enc").write_bytes(cifrar(clave, respuesta_alertas(d, tabla)))
        print(f"[publicar] alertas {d} dias: {time.time() - t:.0f} s", flush=True)

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
