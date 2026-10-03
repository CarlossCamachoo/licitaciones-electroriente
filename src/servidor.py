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
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
import yaml

import competencia
import documentos as docs
import mercado
import notificaciones
import radar

WEB = radar.RAIZ / "web"
HOST = "127.0.0.1"
PUERTO_POR_DEFECTO = 8765
VIGENCIA_CACHE = 1800  # segundos: SECOP es lento; se consulta cada 30 minutos, no en cada clic
INTERVALO_VIGILANCIA = 1800
DIAS_VIGILADOS = 7      # periodo que se consulta solo y alimenta la campana

# Archivos fijos de web/ que se sirven tal cual (logo, iconos, manifiesto).
ESTATICOS = {
    "/logo.webp": ("logo.webp", "image/webp"),
    "/favicon.png": ("favicon-32.png", "image/png"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
}

_cache = {}


def puerto_libre(puerto):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, puerto)) != 0


_candado_calculo = threading.Lock()


PERIODOS = (3, 7, 15, 30)   # dias que ofrece el panel; 60 y 90 se quitaron: casi todo lo viejo es «regimen especial» sin cierre
PERIODO_MAX = max(PERIODOS)


def _construir_base():
    """Una sola consulta a SECOP de los ultimos 30 dias; de ahi salen todos los periodos mas cortos."""
    perfil, filtros = radar.cargar_config()
    minimo = filtros["puntaje"]["umbral_revisar"]
    total, truncado, paginas = radar.recorrer_secop(
        PERIODO_MAX, excluir_modalidades=filtros.get("excluir_modalidad", []))
    resultados, por_dia = [], {}
    for pagina in paginas:
        for p in pagina:
            dia = (p.get("fecha_de_publicacion_del") or "")[:10]
            por_dia[dia] = por_dia.get(dia, 0) + 1          # para contar «procesos revisados» de cada periodo
            r = radar.evaluar(p, perfil, filtros, minimo)
            if r:
                resultados.append(r)
    # Mejor puntaje primero; a igualdad, el mas reciente.
    resultados.sort(key=lambda r: r["fecha_publicacion"], reverse=True)
    resultados.sort(key=lambda r: r["puntaje"], reverse=True)
    return {"resultados": resultados, "por_dia": por_dia, "truncado": truncado,
            "umbral": filtros["puntaje"]["umbral_alerta"],
            "generado": time.strftime("%Y-%m-%d %H:%M"), "generado_ts": int(time.time())}


def _recortar(base, dias):
    """Los datos de los ultimos `dias` dias a partir de la consulta de 30."""
    corte = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    return {"revisados": sum(n for d, n in base["por_dia"].items() if d >= corte),
            "truncado": base["truncado"], "umbral": base["umbral"],
            "generado": base["generado"], "generado_ts": base["generado_ts"], "dias": dias,
            "resultados": [r for r in base["resultados"] if r["fecha_publicacion"] >= corte]}


def calcular(dias, forzar=False):
    """Alertas de los ultimos `dias` dias (3, 7, 15 o 30). Todos salen de la misma consulta de 30 dias,
    guardada 30 minutos: cambiar de periodo no vuelve a llamar a SECOP."""
    dias = min(max(1, dias), PERIODO_MAX)
    # Un solo calculo a la vez: si dos pestanas piden lo mismo, la segunda
    # espera y encuentra el resultado en cache en vez de repetir la descarga.
    with _candado_calculo:
        guardado = _cache.get("base")
        if not guardado or forzar or time.time() - guardado["t"] >= VIGENCIA_CACHE:
            base = _construir_base()
            guardado = _cache["base"] = {"t": time.time(), "datos": base}
            notificaciones.registrar(_recortar(base, DIAS_VIGILADOS)["resultados"])
        return _recortar(guardado["datos"], dias)


_vigilancia = {"ultima_ts": 0, "proxima_ts": 0, "error": ""}


def vigilar():
    """Consulta SECOP cada 30 minutos sin que nadie pulse Actualizar."""
    while True:
        try:
            calcular(DIAS_VIGILADOS, forzar=True)
            _vigilancia.update(ultima_ts=int(time.time()), error="")
        except Exception as e:   # un fallo de red no debe matar la vigilancia
            _vigilancia["error"] = "No se pudo consultar SECOP." if isinstance(e, requests.RequestException) else "Error inesperado."
            sys.stderr.write(f"[vigilancia] {e!r}\n")
        _vigilancia["proxima_ts"] = int(time.time()) + INTERVALO_VIGILANCIA
        time.sleep(INTERVALO_VIGILANCIA)


def pendientes():
    ruta = radar.RAIZ / "config" / "pendientes.yaml"
    with open(ruta, encoding="utf-8") as f:
        lista = (yaml.safe_load(f) or {}).get("pendientes", [])
    return [{"titulo": p.get("titulo", ""),
             "criticidad": p.get("criticidad", ""),
             "necesito": " ".join(str(p.get("necesito", "")).split()),
             "resuelto": bool(p.get("resuelto"))} for p in lista]


def hoja_equipo():
    """Direccion y clave de la hoja compartida del equipo (Google Sheets), o {} si no esta configurada.

    Salen de las variables HOJA_URL y HOJA_TOKEN o de config/hoja.yaml (fuera de git)."""
    url, token = os.environ.get("HOJA_URL", ""), os.environ.get("HOJA_TOKEN", "")
    ruta = radar.RAIZ / "config" / "hoja.yaml"
    if not (url and token) and ruta.exists():
        try:
            d = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
            url, token = str(d.get("url", "")), str(d.get("token", ""))
        except (OSError, yaml.YAMLError):
            url = token = ""
    return {"url": url, "token": token} if url.startswith(("https://", "http://127.0.0.1")) and token else {}


def nombre_propio(texto):
    """Mayuscula inicial en cada palabra, salvo particulas («de», «del», «la», «y»...)."""
    particulas = {"de", "del", "la", "las", "los", "y", "e", "van", "von"}
    palabras = " ".join(str(texto or "").split()).lower().split(" ")
    return " ".join(p if (i and p in particulas) else re.sub(r"(^|[-'])(\w)", lambda m: m.group(1) + m.group(2).upper(), p)
                    for i, p in enumerate(palabras)).strip()


def persona_local():
    """Nombre de quien usa este panel (config/hoja.yaml, clave `persona`), para no preguntarlo."""
    nombre = os.environ.get("HOJA_PERSONA", "")
    ruta = radar.RAIZ / "config" / "hoja.yaml"
    if not nombre and ruta.exists():
        try:
            nombre = str((yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}).get("persona", "") or "")
        except (OSError, yaml.YAMLError):
            nombre = ""
    return nombre_propio(nombre)[:60]


CAMPOS_HOJA = ("id", "estado", "persona", "entidad", "objeto", "valor", "cierre", "puntaje",
               "factibilidad", "departamento", "modalidad", "tipo", "url")


def enviar_a_hoja(item):
    """Reenvia a la hoja del equipo (Google Sheets) un «Me interesa» o su cambio. Devuelve {ok: bool}."""
    cfg = hoja_equipo()
    if not cfg or not isinstance(item, dict):
        return {"ok": False, "error": "La hoja del equipo no esta configurada."}
    carga = {k: item.get(k, "") for k in CAMPOS_HOJA}
    carga["token"] = cfg["token"]
    try:
        r = requests.post(cfg["url"], data=json.dumps(carga).encode("utf-8"), timeout=30,
                          headers={"Content-Type": "text/plain;charset=utf-8"})
        resultado = r.json()
    except (requests.RequestException, ValueError):
        return {"ok": False, "error": "No se pudo hablar con la hoja."}
    return {"ok": bool(resultado.get("ok")), "error": resultado.get("error") or ""}


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
            if url.path == "/api/hoja":
                try:
                    largo = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    return self._json(411, {"error": "Falta el tamaño."})
                if largo > 20000:
                    return self._json(413, {"error": "Demasiado grande."})
                try:
                    item = json.loads(self.rfile.read(largo))
                except ValueError:
                    return self._json(400, {"error": "Datos no validos."})
                return self._json(200, enviar_a_hoja(item))
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
            elif url.path == "/api/notificaciones/leer":
                notificaciones.marcar_leidas()
                self._json(200, {"ok": True})
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
        elif url.path in ESTATICOS:
            nombre, tipo = ESTATICOS[url.path]
            self._enviar(200, (WEB / nombre).read_bytes(), tipo)
        elif url.path == "/api/alertas":
            q = parse_qs(url.query)
            try:
                dias = max(1, min(PERIODO_MAX, int(q.get("dias", ["7"])[0])))
            except ValueError:
                return self._json(400, {"error": "dias debe ser un numero"})
            # «Actualizar» pide una consulta nueva a SECOP (forzar=1), pero no mas de una por minuto.
            forzar = q.get("forzar", ["0"])[0] == "1"
            guardado = _cache.get("base")
            if forzar and guardado and time.time() - guardado["t"] < 60:
                forzar = False
            try:
                datos = calcular(dias, forzar)
                cats = docs.listar()
                tabla = mercado.historial()
                self._json(200, {**datos, "documentos_generales": docs.generales(cats),
                                "mercado": mercado.estado(),
                                "resultados": [
                    {**r, "documentos": docs.requisitos(r, cats),
                     "historial": mercado.historial_de(r["entidad"], tabla),
                     "renovacion": mercado.renovacion_de(r["entidad"], r["coincidencias"]),
                     "competencia": competencia.de_alerta(r["entidad"], r["coincidencias"])}
                    for r in datos["resultados"]]})
            except requests.RequestException:
                self._json(502, {"error": "No se pudo consultar SECOP. "
                                          "Revise la conexion e intente de nuevo."})
        elif url.path == "/api/vencimientos":
            mercado.refrescar_en_segundo_plano()
            self._json(200, {"estado": mercado.estado(),
                             "contratos": mercado.vencimientos()})
        elif url.path == "/api/mercado":
            mercado.refrescar_en_segundo_plano()
            competencia.refrescar_en_segundo_plano()
            self._json(200, {"estado": mercado.estado(),
                             "contratos": mercado.contratos_del_ano(),
                             "competencia": competencia.para_mercado()})
        elif url.path == "/api/notificaciones":
            self._json(200, {**notificaciones.listar(), **_vigilancia,
                             "intervalo_min": INTERVALO_VIGILANCIA // 60})
        elif url.path == "/api/pendientes":
            self._json(200, pendientes())
        elif url.path == "/api/documentos":
            self._json(200, docs.listar())
        elif url.path == "/api/criterios":
            self._json(200, criterios())
        elif url.path == "/api/hoja":
            # Solo dice si hay hoja configurada: la direccion y la clave no salen del servidor.
            self._json(200, {"servidor": True, "persona": persona_local()} if hoja_equipo() else {})
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
    mercado.refrescar_en_segundo_plano()
    competencia.refrescar_en_segundo_plano()
    threading.Thread(target=vigilar, daemon=True).start()
    print(f"Panel en http://{HOST}:{args.puerto}  (Ctrl+C para cerrar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrado.")


if __name__ == "__main__":
    main()
