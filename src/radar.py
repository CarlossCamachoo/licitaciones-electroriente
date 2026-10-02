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
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yaml

RAIZ = Path(__file__).resolve().parent.parent
API_PROCESOS = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
TIEMPO_ESPERA = 60
TAMANO_PAGINA = 5000
LIMITE_POR_DEFECTO = 50000


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


def contiene(texto_norm, termino):
    """Busca el termino como palabra, no como fragmento.

    Evita que 'ups' coincida dentro de 'grupos' o 'obra' dentro de 'obrar'.
    """
    patron = r"(?<![a-z0-9])" + re.escape(normalizar(termino)) + r"(?![a-z0-9])"
    return re.search(patron, texto_norm) is not None


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

def consultar_secop(dias, limite=LIMITE_POR_DEFECTO):
    """Trae procesos publicados en los ultimos N dias, paginando.

    Se filtra por fecha en el servidor para no descargar de mas.
    El filtrado por contenido se hace despues, en local, porque es
    mas facil de auditar y de ajustar.

    Devuelve (procesos, truncado). Si truncado es True, habia mas
    procesos que el limite y el resultado esta incompleto.
    """
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%dT00:00:00.000")
    cabeceras = {}
    token = os.environ.get("SOCRATA_APP_TOKEN")  # opcional, evita limites de uso
    if token:
        cabeceras["X-App-Token"] = token

    procesos = []
    while len(procesos) < limite:
        parametros = {
            "$where": f"fecha_de_publicacion_del > '{desde}'",
            "$limit": min(TAMANO_PAGINA, limite - len(procesos)),
            "$offset": len(procesos),
            # id_del_proceso como desempate: sin orden estable la paginacion
            # puede repetir o saltarse filas.
            "$order": "fecha_de_publicacion_del DESC, id_del_proceso",
        }
        respuesta = requests.get(API_PROCESOS, params=parametros,
                                 headers=cabeceras, timeout=TIEMPO_ESPERA)
        respuesta.raise_for_status()
        pagina = respuesta.json()
        procesos.extend(pagina)
        if len(pagina) < parametros["$limit"]:
            return procesos, False
    return procesos, True


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

def evaluar(proceso, perfil, filtros, solo_abiertos=True):
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
    if solo_abiertos and apertura and apertura != "Abierto":
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

    puntaje = max(0, min(100, puntaje))
    if puntaje < ajustes["umbral_alerta"]:
        return None

    return {
        "puntaje": puntaje,
        "requiere_aliado": requiere_aliado,
        "entidad": limpiar(proceso.get("entidad", "")),
        "departamento": departamento,
        "referencia": limpiar(proceso.get("referencia_del_proceso", "")),
        "descripcion": limpiar(texto).strip()[:400],
        "modalidad": modalidad,
        "tipo_contrato": proceso.get("tipo_de_contrato", ""),
        "estado": proceso.get("estado_del_procedimiento", ""),
        "fase": proceso.get("fase", ""),
        "valor_cop": valor,
        "fecha_publicacion": (proceso.get("fecha_de_publicacion_del") or "")[:10],
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
    ap.add_argument("--incluir-cerrados", action="store_true",
                    help="no descarta procesos que ya cerraron")
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
            procesos, truncado = consultar_secop(args.dias, args.limite)
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
        veredicto = evaluar(p, perfil, filtros, not args.incluir_cerrados)
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
