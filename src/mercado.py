"""
Mercado: lo que las entidades ya contrataron de lo que Electroriente vende.

Sale de los contratos firmados en SECOP II (datos abiertos). Sirve para dos cosas:
  - Proximos vencimientos: contratos que terminan pronto y que la entidad
    probablemente vuelva a contratar. Es una pista, no una garantia: pueden
    prorrogarlos o no renovarlos.
  - Historial de la entidad: cuantos contratos parecidos firmo en el ultimo
    ano, por cuanto y con quien. Ayuda a decidir y da un precio de referencia.

Se usan los mismos terminos de config/filtros.yaml que el radar. Se descarga
una sola vez al dia y se guarda en data/mercado.json.
"""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

import radar

URL = "https://www.datos.gov.co/resource/jbjy-vk9h.json"
RUTA = radar.RAIZ / "data" / "mercado.json"
VIGENCIA = 12 * 3600      # segundos: los contratos no cambian minuto a minuto
MESES_HISTORIAL = 12
DIAS_VENCIMIENTO = 180    # ventana de contratos que terminan pronto

COLUMNAS = ("id_contrato,nombre_entidad,departamento,objeto_del_contrato,"
            "tipo_de_contrato,valor_del_contrato,fecha_de_firma,"
            "fecha_de_fin_del_contrato,proveedor_adjudicado,urlproceso")

_candado = threading.Lock()
_estado = {"calculando": False, "error": ""}
_memoria = {"t": 0, "datos": None}


# La busqueda de texto de Socrata (`$q`) es rapida pero distingue tildes:
# 'iluminacion' y 'iluminación' son busquedas distintas. Se consultan las dos.
CON_TILDE = {"electrico": "eléctrico", "electricos": "eléctricos", "electrica": "eléctrica",
             "electricas": "eléctricas", "iluminacion": "iluminación",
             "automatizacion": "automatización", "proteccion": "protección",
             "protecciones": "protecciones", "instalacion": "instalación",
             "energia": "energía", "subestacion": "subestación", "tension": "tensión",
             "publico": "público", "automatico": "automático", "calidad": "calidad",
             "eficiencia": "eficiencia", "velocidad": "velocidad"}


def _variantes(termino):
    t = radar.normalizar(termino)
    con = " ".join(CON_TILDE.get(w, w) for w in t.split())
    return [t] if con == t else [t, con]


def _consultar(consulta, donde):
    filas, pagina, inicio = [], 5000, 0
    while True:
        lote = radar._pedir_pagina({
            "$select": COLUMNAS, "$where": donde, "$q": consulta,
            "$limit": str(pagina), "$offset": str(inicio),
            "$order": "id_contrato"}, {}, url=URL)
        filas.extend(lote)
        if len(lote) < pagina:
            return filas
        inicio += pagina


def _descargar(filtros):
    """Contratos que mencionan algun termino del radar: firmados en el ultimo
    ano o que terminan en la ventana de vencimientos. Sin duplicados."""
    consultas = sorted({v for g in filtros["incluir"].values()
                        for t in g["terminos"] for v in _variantes(t)})
    hoy = datetime.now()
    desde = (hoy - timedelta(days=30 * MESES_HISTORIAL)).strftime("%Y-%m-%dT00:00:00")
    ini = hoy.strftime("%Y-%m-%dT00:00:00")
    fin = (hoy + timedelta(days=DIAS_VENCIMIENTO)).strftime("%Y-%m-%dT00:00:00")
    donde = (f"fecha_de_firma >= '{desde}' OR "
             f"fecha_de_fin_del_contrato between '{ini}' and '{fin}'")
    unicos = {}
    with ThreadPoolExecutor(max_workers=radar.HILOS) as pool:
        for filas in pool.map(lambda q: _consultar(q, donde), consultas):
            for c in filas:
                unicos[c.get("id_contrato")] = c
    return list(unicos.values())


def _aceptable(c, filtros):
    """Mismo criterio del radar: coincide con lo que vendemos, sin excluidos,
    y no es un servicio disfrazado."""
    texto = radar.normalizar(c.get("objeto_del_contrato", ""))
    if not texto or any(radar.contiene(texto, t) for t in filtros.get("excluir", [])):
        return None
    coincide = sorted({t for g in filtros["incluir"].values()
                       for t in g["terminos"] if radar.contiene(texto, t)})
    if not coincide:
        return None
    aj = filtros.get("ajustes_contrato", {}).get("desfavorables", {})
    tipo = c.get("tipo_de_contrato", "")
    if tipo in aj.get("tipos", []) and not any(
            radar.contiene(texto, t) for t in aj.get("salvo_si_menciona", [])):
        return None
    return coincide


def _limpio(c, coincide, favorables):
    return {
        "id": radar.limpiar(c.get("id_contrato", "")),
        "entidad": radar.limpiar(c.get("nombre_entidad", "")),
        "departamento": radar.limpiar(c.get("departamento", "")),
        "objeto": radar.limpiar(" ".join(str(c.get("objeto_del_contrato", "")).split())),
        "tipo": radar.limpiar(c.get("tipo_de_contrato", "")),
        "valor": radar.a_numero(c.get("valor_del_contrato")),
        "firma": (c.get("fecha_de_firma") or "")[:10],
        "fin": (c.get("fecha_de_fin_del_contrato") or "")[:10],
        "proveedor": radar.limpiar(c.get("proveedor_adjudicado", "")),
        "url": radar.url_segura(c.get("urlproceso")),
        "coincidencias": coincide,
        # Suministro o compraventa: lo que Electroriente hace. El resto (obra,
        # convenios, servicios) se muestra solo si se pide.
        "afin": c.get("tipo_de_contrato", "") in favorables,
    }


def _construir():
    _, filtros = radar.cargar_config()
    favorables = filtros.get("ajustes_contrato", {}).get("favorables", {}).get("tipos", [])
    contratos = []
    for c in _descargar(filtros):
        coincide = _aceptable(c, filtros)
        if coincide:
            contratos.append(_limpio(c, coincide, favorables))
    datos = {"generado_ts": int(time.time()),
             "generado": time.strftime("%Y-%m-%d %H:%M"),
             "contratos": contratos}
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    tmp = RUTA.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.replace(tmp, RUTA)
    return datos


def _leer_disco():
    try:
        with open(RUTA, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def datos_listos():
    """Datos en memoria o en disco, aunque esten viejos. None si no hay nada."""
    if _memoria["datos"] is None:
        _memoria["datos"] = _leer_disco()
    return _memoria["datos"]


def _vigente(datos):
    return datos is not None and time.time() - datos["generado_ts"] < VIGENCIA


def refrescar_en_segundo_plano():
    """Actualiza sin bloquear al panel. Si ya esta vigente o ya corre, no hace nada."""
    with _candado:
        if _estado["calculando"] or _vigente(datos_listos()):
            return
        _estado.update(calculando=True, error="")

    def trabajo():
        try:
            datos = _construir()
            _memoria.update(t=time.time(), datos=datos)
        except requests.RequestException:
            _estado["error"] = "No se pudo consultar SECOP."
        finally:
            _estado["calculando"] = False

    threading.Thread(target=trabajo, daemon=True).start()


def estado():
    d = datos_listos()
    return {"listo": d is not None, "calculando": _estado["calculando"],
            "error": _estado["error"], "generado": d["generado"] if d else ""}


def _clave(entidad):
    return radar.normalizar(entidad)


def vencimientos(dias=DIAS_VENCIMIENTO):
    """Contratos que terminan en los proximos `dias`, el mas cercano primero."""
    d = datos_listos()
    if d is None:
        return []
    hoy = datetime.now().date()
    limite = hoy + timedelta(days=dias)
    salida = []
    for c in d["contratos"]:
        if not c["fin"]:
            continue
        try:
            fin = datetime.strptime(c["fin"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if hoy <= fin <= limite:
            salida.append({**c, "dias": (fin - hoy).days})
    salida.sort(key=lambda c: (c["dias"], -(c["valor"] or 0)))
    return salida


_memo_historial = {"ts": None, "tabla": {}}


def historial():
    """{entidad normalizada: resumen de contratos de suministro o compraventa
    firmados en el ultimo ano}."""
    d = datos_listos()
    if d is None:
        return {}
    if _memo_historial["ts"] == d["generado_ts"]:
        return _memo_historial["tabla"]
    desde = (datetime.now() - timedelta(days=30 * MESES_HISTORIAL)).strftime("%Y-%m-%d")
    por_entidad = {}
    for c in d["contratos"]:
        if c["firma"] and c["firma"] >= desde and c.get("afin"):
            por_entidad.setdefault(_clave(c["entidad"]), []).append(c)
    resumen = {}
    for clave, lista in por_entidad.items():
        provs = {}
        for c in lista:
            p = provs.setdefault(c["proveedor"] or "Sin proveedor", {"n": 0, "total": 0.0})
            p["n"] += 1
            p["total"] += c["valor"] or 0
        top = sorted(provs.items(), key=lambda kv: (-kv[1]["n"], -kv[1]["total"]))[:3]
        valores = [c["valor"] for c in lista if c["valor"]]
        resumen[clave] = {
            "n": len(lista),
            "total": sum(valores),
            "mediana": sorted(valores)[len(valores) // 2] if valores else 0,
            "proveedores": [{"nombre": n, "n": v["n"], "total": v["total"]} for n, v in top],
        }
    _memo_historial.update(ts=d["generado_ts"], tabla=resumen)
    return resumen


def historial_de(entidad, tabla):
    return tabla.get(_clave(entidad))
