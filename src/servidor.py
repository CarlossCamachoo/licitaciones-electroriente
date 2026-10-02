#!/usr/bin/env python3
"""
Panel local del radar de licitaciones.

    python src/servidor.py              # http://127.0.0.1:8765
    python src/servidor.py --puerto 9000

Solo escucha en 127.0.0.1: nadie mas en la red puede abrirlo.
Antes de arrancar comprueba que el puerto este libre.
"""

import argparse
import json
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
import yaml

import radar

WEB = radar.RAIZ / "web"
HOST = "127.0.0.1"
PUERTO_POR_DEFECTO = 8765
VIGENCIA_CACHE = 600  # segundos: SECOP es lento, no se consulta en cada clic

_cache = {}


def puerto_libre(puerto):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, puerto)) != 0


def calcular(dias, cerrados):
    clave = (dias, cerrados)
    guardado = _cache.get(clave)
    if guardado and time.time() - guardado["t"] < VIGENCIA_CACHE:
        return guardado["datos"]

    perfil, filtros = radar.cargar_config()
    procesos, truncado = radar.consultar_secop(dias)
    resultados = [r for r in (radar.evaluar(p, perfil, filtros, not cerrados)
                              for p in procesos) if r]
    resultados.sort(key=lambda r: r["puntaje"], reverse=True)
    datos = {
        "revisados": len(procesos),
        "truncado": truncado,
        "umbral": filtros["puntaje"]["umbral_alerta"],
        "generado": time.strftime("%Y-%m-%d %H:%M"),
        "resultados": resultados,
    }
    _cache[clave] = {"t": time.time(), "datos": datos}
    return datos


def pendientes():
    ruta = radar.RAIZ / "config" / "pendientes.yaml"
    with open(ruta, encoding="utf-8") as f:
        lista = (yaml.safe_load(f) or {}).get("pendientes", [])
    return [{"titulo": p.get("titulo", ""),
             "criticidad": p.get("criticidad", ""),
             "necesito": " ".join(str(p.get("necesito", "")).split()),
             "resuelto": bool(p.get("resuelto"))} for p in lista]


def documentos():
    ruta = radar.RAIZ / "config" / "documentos.yaml"
    with open(ruta, encoding="utf-8") as f:
        cats = (yaml.safe_load(f) or {}).get("categorias", [])
    texto = lambda v: " ".join(str(v or "").split())
    return [{"id": texto(c.get("id")),
             "titulo": texto(c.get("titulo")),
             "descripcion": texto(c.get("descripcion")),
             "documentos": [{k: texto(d.get(k)) for k in
                             ("id", "nombre", "para_que", "emite", "vigencia",
                              "cuando", "pendiente")}
                            for d in c.get("documentos", [])]}
            for c in cats]


class Manejador(BaseHTTPRequestHandler):
    def _enviar(self, codigo, cuerpo, tipo):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline' "
            "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, codigo, obj):
        self._enviar(codigo, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._enviar(200, (WEB / "index.html").read_bytes(),
                         "text/html; charset=utf-8")
        elif url.path == "/api/alertas":
            q = parse_qs(url.query)
            try:
                dias = max(1, min(90, int(q.get("dias", ["7"])[0])))
            except ValueError:
                return self._json(400, {"error": "dias debe ser un numero"})
            cerrados = q.get("cerrados", ["0"])[0] == "1"
            try:
                self._json(200, calcular(dias, cerrados))
            except requests.RequestException:
                self._json(502, {"error": "No se pudo consultar SECOP. "
                                          "Revisa la conexion e intenta de nuevo."})
        elif url.path == "/api/pendientes":
            self._json(200, pendientes())
        elif url.path == "/api/documentos":
            self._json(200, documentos())
        else:
            self._json(404, {"error": "no encontrado"})

    def log_message(self, formato, *args):
        sys.stderr.write("[panel] " + formato % args + "\n")


def main():
    ap = argparse.ArgumentParser(description="Panel local del radar")
    ap.add_argument("--puerto", type=int, default=PUERTO_POR_DEFECTO)
    args = ap.parse_args()

    if not puerto_libre(args.puerto):
        print(f"El puerto {args.puerto} ya esta en uso. "
              f"Prueba con --puerto <otro>.", file=sys.stderr)
        sys.exit(1)

    servidor = ThreadingHTTPServer((HOST, args.puerto), Manejador)
    print(f"Panel en http://{HOST}:{args.puerto}  (Ctrl+C para cerrar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrado.")


if __name__ == "__main__":
    main()
