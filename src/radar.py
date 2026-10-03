#!/usr/bin/env python3
"""
Radar de licitaciones para Electroriente S.A.S.

Consulta los datos abiertos de SECOP II, filtra los procesos que encajan
con el perfil de la empresa y entrega una lista ordenada por relevancia.

Uso:
    python src/radar.py                    # ultimos 7 dias
    python src/radar.py --dias 30          # ultimos 30 dias
    python src/radar.py --demo             # sin red, con datos de prueba
    python src/radar.py --salida data/hoy.json

No requiere llave de API. Los datos son publicos.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import requests
import yaml

RAIZ = Path(__file__).resolve().parent.parent
API_PROCESOS = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
TIEMPO_ESPERA = 60
TAMANO_PAGINA = 5000
LIMITE_POR_DEFECTO = 300000


# --------------------------------------------------------------------------
# Utilidades de texto
# --------------------------------------------------------------------------

def normalizar(texto):
    """Minusculas, sin tildes. Para comparar sin sorpresas."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFD", str(texto))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto.lower()).strip()


def _formas(palabra):
    """Singular y plural de una palabra (sin tildes): variador, variadores; cable, cables."""
    formas = {palabra}
    if len(palabra) >= 3:
        formas |= {palabra + "s", palabra + "es"}
    if len(palabra) >= 5 and palabra.endswith("es"):
        formas.add(palabra[:-2])
    if len(palabra) >= 4 and palabra.endswith("s"):
        formas.add(palabra[:-1])
    return sorted(formas, key=len, reverse=True)


@lru_cache(maxsize=4096)
def _patron(termino):
    palabras = normalizar(termino).split(" ")
    cuerpo = r"\s+".join(
        "(?:" + "|".join(re.escape(f) for f in _formas(p)) + ")" if len(p) > 2 else re.escape(p)
        for p in palabras)
    return re.compile(r"(?<![a-z0-9])" + cuerpo + r"(?![a-z0-9])")


def contiene(texto_norm, termino):
    """Busca el termino como palabra, no como fragmento, y acepta singular y plural.

    Evita que 'ups' coincida dentro de 'grupos' o 'obra' dentro de 'obrar'.
    Pero 'obra' si coincide con 'obras' y 'variador de velocidad' con
    'variadores de velocidades': cada palabra del termino admite su plural.
    """
    return _patron(termino).search(texto_norm) is not None


def limpiar(texto):
    """Quita caracteres de control del texto que viene de la API.

    Evita que un proceso con secuencias de escape ensucie la terminal.
    """
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(texto or ""))


def a_numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------

def cargar_config():
    with open(RAIZ / "config" / "perfil.yaml", encoding="utf-8") as f:
        perfil = yaml.safe_load(f)
    with open(RAIZ / "config" / "filtros.yaml", encoding="utf-8") as f:
        filtros = yaml.safe_load(f)
    return perfil, filtros


def cargar_pendientes():
    """Lee los pendientes sin resolver. Si el archivo no existe, no falla."""
    ruta = RAIZ / "config" / "pendientes.yaml"
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8") as f:
        datos = yaml.safe_load(f) or {}
    return [p for p in datos.get("pendientes", []) if not p.get("resuelto")]


def avisar_pendientes(pendientes):
    """Muestra lo que falta. Se imprime siempre, para que no se olvide."""
    if not pendientes:
        return

    orden = {"bloqueante": 0, "alta": 1, "media": 2, "baja": 3}
    pendientes = sorted(pendientes, key=lambda p: orden.get(p.get("criticidad"), 9))
    bloqueantes = [p for p in pendientes if p.get("criticidad") == "bloqueante"]

    print()
    print("#" * 78)
    print(f"#  PENDIENTE: {len(pendientes)} cosas sin resolver", end="")
    if bloqueantes:
        print(f", {len(bloqueantes)} BLOQUEANTES")
    else:
        print()
    print("#" * 78)

    for p in pendientes:
        etiqueta = p.get("criticidad", "").upper()
        print(f"\n  [{etiqueta}] {p.get('titulo', '')}")
        necesito = " ".join(str(p.get("necesito", "")).split())
        if necesito:
            print(f"     Falta: {necesito}")

    if bloqueantes:
        print("\n  Mientras haya bloqueantes, trata las alertas de este radar")
        print("  como exploratorias. Puede estar mostrando procesos a los que")
        print("  Electroriente todavia no se puede presentar.")

    print("\n  Detalle y por que importa cada uno: config/pendientes.yaml")
    print("  Cuando resuelvas algo, marca 'resuelto: true' en ese archivo.")
    print("#" * 78 + "\n")


# --------------------------------------------------------------------------
# Consulta a SECOP
# --------------------------------------------------------------------------

def _pedir_pagina(parametros, cabeceras, intentos=4, url=None):
    """Una pagina de SECOP. Reintenta ante errores del servidor o de red:
    el servicio da 503 de forma intermitente y no vale perder una consulta
    de 20 segundos por un fallo pasajero."""
    for intento in range(1, intentos + 1):
        try:
            respuesta = requests.get(url or API_PROCESOS, params=parametros,
                                     headers=cabeceras, timeout=TIEMPO_ESPERA)
            if respuesta.status_code >= 500 or respuesta.status_code == 429:
                respuesta.raise_for_status()
            respuesta.raise_for_status()
            return respuesta.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            reintentable = not isinstance(e, requests.HTTPError) or \
                e.response is None or e.response.status_code >= 500 or e.response.status_code == 429
            if intento == intentos or not reintentable:
                raise
            time.sleep(2 * intento)


# Solo las columnas que el radar usa: baja la descarga a menos de la mitad.
COLUMNAS = ("entidad,departamento_entidad,referencia_del_proceso,"
            "nombre_del_procedimiento,descripci_n_del_procedimiento,"
            "modalidad_de_contratacion,tipo_de_contrato,estado_del_procedimiento,"
            "fase,precio_base,valor_total_adjudicacion,fecha_de_publicacion_del,"
            "urlproceso,estado_de_apertura_del_proceso,id_del_proceso,"
            "fecha_de_recepcion_de,proveedores_unicos_con")
HILOS = 3


def _literal(texto):
    return "'" + str(texto).replace("'", "''") + "'"


def recorrer_secop(dias, limite=LIMITE_POR_DEFECTO, excluir_modalidades=()):
    """Prepara la descarga de los procesos de los ultimos N dias.

    Devuelve (total, truncado, paginas): `paginas` es un generador que
    entrega lista tras lista de procesos, en orden, sin acumularlos todos
    en memoria (90 dias son unos 220.000 procesos).

    Solo se descartan en el servidor dos cosas estructurales, no de
    contenido: procesos cuyo estado de apertura no es "Abierto" y las
    modalidades excluidas (contratacion directa). Sin esto, 60 o 90 dias
    no caben. Todo el filtrado por contenido sigue siendo local.
    """
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%dT00:00:00.000")
    donde = (f"fecha_de_publicacion_del > '{desde}' AND "
             "(estado_de_apertura_del_proceso = 'Abierto' "
             "OR estado_de_apertura_del_proceso IS NULL)")
    if excluir_modalidades:
        lista = ", ".join(_literal(m) for m in excluir_modalidades)
        donde += (" AND (modalidad_de_contratacion IS NULL "
                  f"OR modalidad_de_contratacion NOT IN ({lista}))")
    cabeceras = {}
    token = os.environ.get("SOCRATA_APP_TOKEN")  # opcional, evita limites de uso
    if token:
        cabeceras["X-App-Token"] = token

    cuenta = _pedir_pagina({"$select": "count(*) as n", "$where": donde}, cabeceras)
    existentes = int(cuenta[0]["n"]) if cuenta else 0
    total = min(existentes, limite)

    def pagina(desplazamiento):
        return _pedir_pagina({
            "$select": COLUMNAS, "$where": donde,
            "$limit": min(TAMANO_PAGINA, total - desplazamiento),
            "$offset": desplazamiento,
            # id_del_proceso como desempate: sin orden estable la paginacion
            # puede repetir o saltarse filas.
            "$order": "fecha_de_publicacion_del DESC, id_del_proceso",
        }, cabeceras)

    def generar():
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(HILOS) as pool:
            # map entrega en orden aunque las paginas lleguen desordenadas
            yield from pool.map(pagina, range(0, total, TAMANO_PAGINA))

    return total, existentes > limite, generar()


def consultar_secop(dias, limite=LIMITE_POR_DEFECTO, excluir_modalidades=()):
    """Version simple: junta todo en una lista. Devuelve (procesos, truncado)."""
    total, truncado, paginas = recorrer_secop(dias, limite, excluir_modalidades)
    return [p for pag in paginas for p in pag], truncado


def cargar_demo():
    ruta = RAIZ / "data" / "ejemplo_procesos.json"
    if not ruta.exists():
        print(f"No existe el archivo de prueba: {ruta}", file=sys.stderr)
        sys.exit(1)
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Evaluacion de un proceso
# --------------------------------------------------------------------------

def _descripcion_visible(proceso):
    """Texto a mostrar. SECOP suele repetir el nombre dentro de la descripcion
    (o al reves); se muestra una sola vez."""
    nombre = limpiar(proceso.get("nombre_del_procedimiento", "")).strip()
    desc = limpiar(proceso.get("descripci_n_del_procedimiento", "")).strip()
    n, d = normalizar(nombre), normalizar(desc)
    if not n or n == d or n in d:
        texto = desc or nombre
    elif d in n:
        texto = nombre
    else:
        texto = f"{nombre}. {desc}"
    return texto[:400]


def evaluar(proceso, perfil, filtros, umbral=None):
    """Devuelve un dict con el veredicto, o None si no aplica.

    El veredicto siempre explica por que. Si no se puede auditar,
    el area deja de confiar en la herramienta.
    """
    texto = " ".join([
        proceso.get("descripci_n_del_procedimiento", ""),
        proceso.get("nombre_del_procedimiento", ""),
    ])
    texto_norm = normalizar(texto)
    if not texto_norm:
        return None

    # Un proceso cerrado ya no admite ofertas. Si el campo viene vacio
    # no se descarta: es mejor revisar de mas que perder una oportunidad.
    apertura = proceso.get("estado_de_apertura_del_proceso", "")
    if apertura and apertura != "Abierto":
        return None

    # Fecha limite para presentar oferta ("recepcion de respuestas"). SECOP la
    # trae en pocos procesos (cerca del 5 %). Si ya paso, el proceso esta
    # vencido aunque siga marcado "Abierto". Si no viene, no se descarta.
    fecha_cierre = (proceso.get("fecha_de_recepcion_de") or "")[:10]
    if fecha_cierre and fecha_cierre < datetime.now().strftime("%Y-%m-%d"):
        return None

    # --- Paso 1: inclusion y puntaje base -----------------------------
    puntaje = 0
    coincidencias = []
    for nombre_grupo, grupo in filtros["incluir"].items():
        encontrados = [t for t in grupo["terminos"] if contiene(texto_norm, t)]
        if encontrados:
            # El grupo aporta su peso una sola vez, no por cada termino.
            # Asi un pliego que repite palabras no infla el puntaje.
            puntaje += grupo["peso"]
            coincidencias.extend(encontrados)

    if not coincidencias:
        return None

    # --- Paso 2: exclusiones ------------------------------------------
    for termino in filtros["excluir"]:
        if contiene(texto_norm, termino):
            return None

    modalidad = proceso.get("modalidad_de_contratacion", "")
    if modalidad in filtros.get("excluir_modalidad", []):
        return None

    # --- Paso 3: ajustes de puntaje -----------------------------------
    ajustes = filtros["puntaje"]
    notas = []

    departamento = proceso.get("departamento_entidad", "")
    if departamento in perfil["territorio_prioritario"]:
        puntaje += ajustes["bono_territorio_prioritario"]
        notas.append(f"territorio prioritario ({departamento})")

    entidad_norm = normalizar(proceso.get("entidad", ""))
    for conocida in filtros.get("entidades_conocidas", []):
        if normalizar(conocida) in entidad_norm:
            puntaje += ajustes["bono_entidad_conocida"]
            notas.append("entidad que ya compra este material")
            break

    # Cuantia. Si viene en cero, no penalizamos: muchos procesos
    # publican el valor despues. Se marca para revision manual.
    valor = a_numero(proceso.get("precio_base")) or a_numero(
        proceso.get("valor_total_adjudicacion"))
    cap = perfil["capacidad"]
    if valor == 0:
        notas.append("sin valor publicado, revisar manualmente")
    elif valor < cap["cuantia_minima_cop"]:
        puntaje += ajustes["penalizacion_fuera_de_cuantia"]
        notas.append("cuantia por debajo del minimo util")
    elif valor > cap["cuantia_maxima_union_temporal_cop"]:
        puntaje += ajustes["penalizacion_fuera_de_cuantia"]
        notas.append("cuantia muy por encima de la capacidad")
    elif valor > cap["cuantia_maxima_sola_cop"]:
        notas.append("cuantia alta, evaluar union temporal")

    # --- Union temporal: se marca, no se descarta ---------------------
    union = filtros.get("marcar_union_temporal", {})
    requiere_aliado = False
    if proceso.get("tipo_de_contrato", "") in union.get("tipos_contrato", []):
        requiere_aliado = True
    if any(contiene(texto_norm, t) for t in union.get("terminos", [])):
        requiere_aliado = True
    if requiere_aliado and not perfil["modalidad_participacion"]["obra_con_instalacion"]:
        notas.append("incluye obra o montaje, requiere aliado instalador")
        # Baja la factibilidad, pero no lo descarta: queda en "por revisar".
        puntaje += ajustes.get("penalizacion_requiere_aliado", 0)

    # Tipo de contrato y modalidad: lo que Electroriente hace de verdad
    # (suministro) contra lo que no (servicios, informacion sin oferta).
    tipo = proceso.get("tipo_de_contrato", "")
    fav = filtros.get("ajustes_contrato", {}).get("favorables", {})
    des = filtros.get("ajustes_contrato", {}).get("desfavorables", {})
    if tipo in fav.get("tipos", []):
        puntaje += fav["bono"]
        notas.append(f"contrato de {tipo.lower()}")
    elif tipo in des.get("tipos", []) and not any(
            contiene(texto_norm, t) for t in des.get("salvo_si_menciona", [])):
        puntaje += des["penalizacion"]
        notas.append(f"contrato de {tipo.lower()}, poco afin")
    man = filtros.get("ajustes_contrato", {}).get("mantenimiento", {})
    tope_mantenimiento = None
    if man and any(contiene(texto_norm, t) for t in man.get("terminos", [])) and not any(
            contiene(texto_norm, t) for t in man.get("salvo_si_menciona", [])):
        puntaje += man["penalizacion"]
        tope_mantenimiento = man.get("tope_puntaje")
        notas.append("mantenimiento o reparacion: es servicio, no suministro")
    mod_fav = filtros.get("ajustes_modalidad", {}).get("favorables", {})
    mod_info = filtros.get("ajustes_modalidad", {}).get("solo_informacion", {})
    if modalidad in mod_fav.get("modalidades", []):
        puntaje += mod_fav["bono"]
    elif modalidad in mod_info.get("modalidades", []):
        puntaje += mod_info["penalizacion"]
        notas.append("solo solicitud de informacion, no es oferta")

    puntaje = max(0, min(100, puntaje))
    if tope_mantenimiento is not None:
        puntaje = min(puntaje, tope_mantenimiento)
    if puntaje < (ajustes["umbral_alerta"] if umbral is None else umbral):
        return None
    niveles = filtros.get("niveles", {"alta": 50, "media": 30})
    nivel = ("alta" if puntaje >= niveles["alta"] else
             "media" if puntaje >= niveles["media"] else "revisar")

    return {
        "id": limpiar(proceso.get("id_del_proceso", "")),
        "puntaje": puntaje,
        "nivel": nivel,
        "requiere_aliado": requiere_aliado,
        "entidad": limpiar(proceso.get("entidad", "")),
        "departamento": departamento,
        "referencia": limpiar(proceso.get("referencia_del_proceso", "")),
        "descripcion": _descripcion_visible(proceso),
        "modalidad": modalidad,
        "tipo_contrato": proceso.get("tipo_de_contrato", ""),
        "estado": proceso.get("estado_del_procedimiento", ""),
        "fase": proceso.get("fase", ""),
        "valor_cop": valor,
        "fecha_publicacion": (proceso.get("fecha_de_publicacion_del") or "")[:10],
        "fecha_cierre": fecha_cierre,
        # Proveedores distintos que ya respondieron al proceso (oferta o, en las
        # solicitudes de informacion, su respuesta). None si SECOP no lo trae.
        "respondieron": (int(a_numero(proceso["proveedores_unicos_con"]))
                         if proceso.get("proveedores_unicos_con") not in (None, "") else None),
        "url": url_segura(proceso.get("urlproceso")),
        "coincidencias": sorted(set(coincidencias)),
        "notas": notas,
    }


# --------------------------------------------------------------------------
# Presentacion
# --------------------------------------------------------------------------

def url_segura(valor):
    """Devuelve la URL solo si es https; si no, cadena vacia."""
    if isinstance(valor, dict):
        valor = valor.get("url", "")
    valor = limpiar(valor).strip()
    return valor if valor.startswith("https://") else ""


def pesos(valor):
    if not valor:
        return "sin valor publicado"
    return f"${valor:,.0f} COP".replace(",", ".")


def imprimir(resultados):
    if not resultados:
        print("\nNingun proceso supero el umbral en este periodo.\n")
        print("Si esto se repite varios dias, revisa config/filtros.yaml:")
        print("  - puede que el umbral_alerta este muy alto")
        print("  - o que falten terminos en la seccion 'incluir'\n")
        return

    print(f"\n{len(resultados)} procesos encontrados\n")
    print("=" * 78)
    for i, r in enumerate(resultados, 1):
        marca = "  [REQUIERE ALIADO]" if r["requiere_aliado"] else ""
        print(f"\n{i}. [{r['puntaje']}/100] {r['entidad']}{marca}")
        print(f"   {r['departamento']} | {r['fecha_publicacion']} | {pesos(r['valor_cop'])}")
        print(f"   Modalidad: {r['modalidad']} | Estado: {r['estado']}")
        print(f"   {r['descripcion'][:200]}")
        print(f"   Coincide por: {', '.join(r['coincidencias'][:6])}")
        for nota in r["notas"]:
            print(f"   Nota: {nota}")
        if r["url"]:
            print(f"   {r['url']}")
    print("\n" + "=" * 78 + "\n")


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Radar de licitaciones Electroriente")
    ap.add_argument("--dias", type=int, default=7,
                    help="dias hacia atras a revisar (por defecto 7)")
    ap.add_argument("--demo", action="store_true",
                    help="usa datos locales de prueba, sin conexion")
    ap.add_argument("--salida", help="guarda el resultado en un archivo JSON")
    ap.add_argument("--limite", type=int, default=LIMITE_POR_DEFECTO,
                    help="maximo de procesos a descargar (por defecto %d)"
                    % LIMITE_POR_DEFECTO)
    ap.add_argument("--sin-avisos", action="store_true",
                    help="oculta el recordatorio de pendientes")
    args = ap.parse_args()

    perfil, filtros = cargar_config()
    pendientes = [] if args.sin_avisos else cargar_pendientes()

    if args.demo:
        print("Modo demo: usando data/ejemplo_procesos.json")
        procesos = cargar_demo()
        truncado = False
    else:
        print(f"Consultando SECOP II, ultimos {args.dias} dias...")
        try:
            procesos, truncado = consultar_secop(
                args.dias, args.limite, filtros.get("excluir_modalidad", []))
        except requests.RequestException as e:
            print(f"\nError al consultar SECOP: {e}", file=sys.stderr)
            print("Revisa la conexion. Los datos abiertos no requieren llave.",
                  file=sys.stderr)
            sys.exit(1)

    print(f"Revisados: {len(procesos)} procesos")
    if truncado:
        print(f"AVISO: se alcanzo el limite de {args.limite} y habia mas procesos.")
        print("       El resultado esta incompleto. Sube --limite o reduce --dias.")

    resultados = []
    for p in procesos:
        veredicto = evaluar(p, perfil, filtros)
        if veredicto:
            resultados.append(veredicto)

    resultados.sort(key=lambda r: r["puntaje"], reverse=True)
    imprimir(resultados)

    if args.salida:
        ruta = Path(args.salida)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)
        print(f"Guardado en {ruta}\n")

    # El aviso va al final para que quede como lo ultimo que se lee.
    avisar_pendientes(pendientes)


if __name__ == "__main__":
    main()
