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
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
import yaml

import documentos as docs
import radar

WEB = radar.RAIZ / "web"
HOST = "127.0.0.1"
PUERTO_POR_DEFECTO = 8765
VIGENCIA_CACHE = 600  # segundos: SECOP es lento, no se consulta en cada clic

_cache = {}


def puerto_libre(puerto):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, puerto)) != 0


_candado_calculo = threading.Lock()


def calcular(dias):
    # Un solo calculo a la vez: si dos pestanas piden lo mismo, la segunda
    # espera y encuentra el resultado en cache en vez de repetir la descarga.
    with _candado_calculo:
        guardado = _cache.get(dias)
        if guardado and time.time() - guardado["t"] < VIGENCIA_CACHE:
            return guardado["datos"]

        perfil, filtros = radar.cargar_config()
        minimo = filtros["puntaje"]["umbral_revisar"]
        total, truncado, paginas = radar.recorrer_secop(
            dias, excluir_modalidades=filtros.get("excluir_modalidad", []))
        resultados, revisados = [], 0
        for pagina in paginas:
            revisados += len(pagina)
            resultados.extend(r for r in (radar.evaluar(p, perfil, filtros, minimo)
                                          for p in pagina) if r)
        # Mejor puntaje primero; a igualdad, el mas reciente.
        resultados.sort(key=lambda r: r["fecha_publicacion"], reverse=True)
        resultados.sort(key=lambda r: r["puntaje"], reverse=True)
        datos = {
            "revisados": revisados,
            "truncado": truncado,
            "umbral": filtros["puntaje"]["umbral_alerta"],
            "generado": time.strftime("%Y-%m-%d %H:%M"),
            "generado_ts": int(time.time()),
            "dias": dias,
            "resultados": resultados,
        }
        _cache[dias] = {"t": time.time(), "datos": datos}
        return datos


def pendientes():
    ruta = radar.RAIZ / "config" / "pendientes.yaml"
    with open(ruta, encoding="utf-8") as f:
        lista = (yaml.safe_load(f) or {}).get("pendientes", [])
    return [{"titulo": p.get("titulo", ""),
             "criticidad": p.get("criticidad", ""),
             "necesito": " ".join(str(p.get("necesito", "")).split()),
             "resuelto": bool(p.get("resuelto"))} for p in lista]


def criterios():
    """Criterios explicados, terminos de busqueda y cuantas veces acerto cada uno."""
    with open(radar.RAIZ / "config" / "criterios.yaml", encoding="utf-8") as f:
        crit = yaml.safe_load(f) or {}
    _, filtros = radar.cargar_config()

    # Aciertos sobre la consulta mas reciente que haya en memoria.
    reciente = max(_cache.values(), key=lambda g: g["t"], default=None)
    aciertos, base = {}, None
    if reciente:
        base = {"generado": reciente["datos"]["generado"],
                "candidatos": len(reciente["datos"]["resultados"])}
        for r in reciente["datos"]["resultados"]:
            for t in r["coincidencias"]:
                aciertos[t] = aciertos.get(t, 0) + 1

    grupos = [{"id": nombre, "peso": g["peso"],
               "terminos": [{"t": t, "n": aciertos.get(radar.normalizar(t), 0)}
                            for t in g["terminos"]]}
              for nombre, g in filtros["incluir"].items()]
    return {"criterios": crit.get("criterios", []),
            "revision": crit.get("revision_semanal", []),
            "grupos": grupos, "excluir": filtros["excluir"], "base": base,
            "puntaje": filtros["puntaje"], "niveles": filtros["niveles"]}


class Manejador(BaseHTTPRequestHandler):
    def _enviar(self, codigo, cuerpo, tipo, extra=None):
        self.send_response(codigo)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
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

    def _local_ok(self):
        """Evita que otra web abra o escriba en el panel (DNS rebinding / CSRF)."""
        puerto = self.server.server_address[1]
        validos = {f"{HOST}:{puerto}", f"localhost:{puerto}"}
        if self.headers.get("Host") not in validos:
            return False
        origen = self.headers.get("Origin")
        return origen is None or origen in {"http://" + h for h in validos}

    def do_POST(self):
        if not self._local_ok() or self.headers.get("X-Panel") != "1":
            return self._json(403, {"error": "Solicitud no permitida."})
        url = urlparse(self.path)
        q = parse_qs(url.query)
        try:
            if url.path == "/api/subir":
                try:
                    largo = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    return self._json(411, {"error": "Falta el tamaño del archivo."})
                if largo > docs.MAX_BYTES:
                    return self._json(413, {"error": "El archivo supera 25 MB."})
                cuerpo = self.rfile.read(largo)
                nombre = unquote(self.headers.get("X-Nombre", ""))
                entrada = docs.guardar(q.get("doc", [""])[0], nombre,
                                       self.headers.get("X-Vence", ""), cuerpo)
                self._json(201, entrada)
            elif url.path == "/api/eliminar":
                docs.eliminar(q.get("id", [""])[0])
                self._json(200, {"ok": True})
            else:
                self._json(404, {"error": "no encontrado"})
        except docs.ErrorDocumento as e:
            self._json(400, {"error": str(e)})

    def do_GET(self):
        if not self._local_ok():
            return self._json(403, {"error": "Solicitud no permitida."})
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
            try:
                datos = calcular(dias)
                cats = docs.listar()
                self._json(200, {**datos, "resultados": [
                    {**r, "documentos": docs.requisitos(r, cats)}
                    for r in datos["resultados"]]})
            except requests.RequestException:
                self._json(502, {"error": "No se pudo consultar SECOP. "
                                          "Revisa la conexion e intenta de nuevo."})
        elif url.path == "/api/pendientes":
            self._json(200, pendientes())
        elif url.path == "/api/documentos":
            self._json(200, docs.listar())
        elif url.path == "/api/criterios":
            self._json(200, criterios())
        elif url.path == "/api/archivo":
            try:
                datos, tipo, ext = docs.abrir(parse_qs(url.query).get("id", [""])[0])
            except docs.ErrorDocumento as e:
                return self._json(404, {"error": str(e)})
            self._enviar(200, datos, tipo, {
                "Content-Disposition": f'attachment; filename="documento{ext}"'})
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
