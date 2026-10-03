"""
Competencia: cuantos proveedores se presentan a los procesos de lo que Electroriente vende.

SECOP publica el conteo de proveedores que respondieron a un proceso solo cuando ya
cerro (en los abiertos casi siempre aparece en 0). Por eso se mide en los procesos
cerrados de los ultimos 12 meses: por entidad, por producto y por departamento.

Solo cuentan las modalidades donde compiten varios (minima cuantia, seleccion
abreviada, licitacion publica): en contratacion directa hay un proveedor elegido
de antemano y el dato no dice nada de la competencia. Los procesos cerrados sin
ninguna respuesta se cuentan aparte como "desiertos".
"""

import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

import mercado
import radar

URL = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
RUTA = radar.RAIZ / "data" / "competencia.json"
VERSION = 1
VIGENCIA = 24 * 3600
MESES = 12
MODALIDADES = ["Mínima cuantía", "Selección Abreviada de Menor Cuantía",
               "Selección abreviada subasta inversa", "Licitación pública",
               "Licitación pública Obra Publica",
               "Seleccion Abreviada Menor Cuantia Sin Manifestacion Interes"]
COLUMNAS = ("id_del_proceso,entidad,departamento_entidad,nombre_del_procedimiento,"
            "descripci_n_del_procedimiento,proveedores_unicos_con")

_candado = threading.Lock()
_estado = {"calculando": False, "error": ""}
_memoria = {"datos": None}


def _descargar(filtros):
    consultas = sorted({v for g in filtros["incluir"].values()
                        for t in g["terminos"] for v in mercado._variantes(t)})
    desde = (datetime.now() - timedelta(days=30 * MESES)).strftime("%Y-%m-%dT00:00:00")
    lista = ", ".join("'" + m + "'" for m in MODALIDADES)
    donde = (f"fecha_de_publicacion_del >= '{desde}' AND "
             f"estado_de_apertura_del_proceso = 'Cerrado' AND "
             f"modalidad_de_contratacion in ({lista})")
    unicos = {}
    with ThreadPoolExecutor(max_workers=radar.HILOS) as pool:
        for filas in pool.map(lambda q: mercado._consultar(
                q, donde, url=URL, columnas=COLUMNAS, orden="id_del_proceso"), consultas):
            for p in filas:
                unicos[p.get("id_del_proceso")] = p
    return list(unicos.values())


def _acumular(tabla, clave, respondieron):
    t = tabla.setdefault(clave, {"n": 0, "suma": 0, "desiertos": 0})
    t["n"] += 1
    t["suma"] += respondieron
    if respondieron == 0:
        t["desiertos"] += 1


def _construir():
    _, filtros = radar.cargar_config()
    entidades, productos, regiones, total = {}, {}, {}, 0
    for p in _descargar(filtros):
        texto = radar.normalizar(" ".join([p.get("nombre_del_procedimiento", ""),
                                           p.get("descripci_n_del_procedimiento", "")]))
        if not texto or any(radar.contiene(texto, t) for t in filtros.get("excluir", [])):
            continue
        tokens = re.findall(r"[a-z0-9]+", texto)
        terminos = {radar.normalizar(t) for g in filtros["incluir"].values()
                    for t in g["terminos"] if mercado._coincide(tokens, t)}
        if not terminos:
            continue
        r = int(radar.a_numero(p.get("proveedores_unicos_con")))
        total += 1
        _acumular(entidades, mercado._clave(p.get("entidad", "")), r)
        _acumular(regiones, radar.normalizar(p.get("departamento_entidad", "")) or "sin departamento", r)
        for t in terminos:
            _acumular(productos, t, r)
    datos = {"version": VERSION, "generado_ts": int(time.time()),
             "generado": time.strftime("%Y-%m-%d %H:%M"), "procesos": total,
             "entidades": entidades, "productos": productos, "regiones": regiones}
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    tmp = RUTA.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.replace(tmp, RUTA)
    return datos


def datos_listos():
    if _memoria["datos"] is None:
        try:
            with open(RUTA, encoding="utf-8") as f:
                _memoria["datos"] = json.load(f)
        except (FileNotFoundError, ValueError):
            pass
    return _memoria["datos"]


def _vigente(d):
    return (d is not None and d.get("version") == VERSION
            and time.time() - d["generado_ts"] < VIGENCIA)


def refrescar_en_segundo_plano():
    with _candado:
        if _estado["calculando"] or _vigente(datos_listos()):
            return
        _estado.update(calculando=True, error="")

    def trabajo():
        try:
            _memoria["datos"] = _construir()
        except requests.RequestException:
            _estado["error"] = "No se pudo consultar SECOP."
        finally:
            _estado["calculando"] = False

    threading.Thread(target=trabajo, daemon=True).start()


def _resumen(t):
    return {"n": t["n"], "promedio": round(t["suma"] / t["n"], 1), "desiertos": t["desiertos"]}


def de_alerta(entidad, coincidencias):
    """Competencia que suele haber: la de la propia entidad si tiene procesos
    cerrados de lo mismo; si no, la del producto. None si no hay datos."""
    d = datos_listos()
    if d is None:
        return None
    e = d["entidades"].get(mercado._clave(entidad))
    if e:
        return {**_resumen(e), "alcance": "entidad"}
    propios = [d["productos"][radar.normalizar(t)] for t in coincidencias
               if radar.normalizar(t) in d["productos"]]
    if propios:
        return {**_resumen(max(propios, key=lambda t: t["n"])), "alcance": "producto"}
    return None


def para_mercado():
    d = datos_listos()
    if d is None:
        return {"entidades": {}, "productos": {}, "regiones": {}}
    return {k: {c: _resumen(t) for c, t in d[k].items()}
            for k in ("entidades", "productos", "regiones")}
