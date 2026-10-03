#!/usr/bin/env python3
"""
Vigilante en la nube: busca en SECOP y avisa al celular de las licitaciones
nuevas de Santander, aunque el computador este apagado.

Lo ejecuta GitHub Actions cada 30 minutos (ver .github/workflows/vigilante.yml).
Tambien se puede probar a mano:

    NTFY_TOPIC=mi-tema python src/vigilante_nube.py            # busca y avisa
    python src/vigilante_nube.py --sin-avisar                   # solo muestra

Que cuenta como "nueva": una alerta (factibilidad alta o media) de una entidad
del departamento de Santander cuyo id no esta en data/vistos_nube.json. Ese
archivo lo conserva GitHub entre ejecuciones (cache). La primera vez no avisa de
lo que ya existe: solo manda un mensaje de prueba para confirmar que el aviso llega.

El tema de ntfy (NTFY_TOPIC) funciona como contrasena: quien lo conozca puede leer
los avisos. Por eso va en un secreto de GitHub y no en el codigo.
"""

import argparse
import json
import os
import sys
import time

import requests

import radar

DIAS = 7
DEPARTAMENTO = "Santander"
NIVELES = ("alta", "media")
MAX_AVISOS = 8          # si aparecen mas de golpe, se manda un resumen del resto
VISTOS = radar.RAIZ / "data" / "vistos_nube.json"
NTFY = "https://ntfy.sh"


def alertas_de_santander():
    perfil, filtros = radar.cargar_config()
    minimo = filtros["puntaje"]["umbral_revisar"]
    total, truncado, paginas = radar.recorrer_secop(
        DIAS, excluir_modalidades=filtros.get("excluir_modalidad", []))
    salida = []
    for pagina in paginas:
        for p in pagina:
            r = radar.evaluar(p, perfil, filtros, minimo)
            if r and r["departamento"] == DEPARTAMENTO and r["nivel"] in NIVELES and r["id"]:
                salida.append(r)
    salida.sort(key=lambda r: r["puntaje"], reverse=True)
    return salida


def leer_vistos():
    try:
        with open(VISTOS, encoding="utf-8") as f:
            return set(json.load(f).get("vistos", []))
    except (FileNotFoundError, ValueError):
        return None   # None = primera vez


def guardar_vistos(ids):
    VISTOS.parent.mkdir(parents=True, exist_ok=True)
    with open(VISTOS, "w", encoding="utf-8") as f:
        json.dump({"vistos": sorted(ids)[-20000:], "actualizado": time.strftime("%Y-%m-%d %H:%M:%S")}, f)


def avisar(tema, titulo, mensaje, enlace="", prioridad=3):
    """Publica en ntfy con JSON (admite tildes en el titulo)."""
    cuerpo = {"topic": tema, "title": titulo, "message": mensaje[:1000],
              "priority": prioridad, "tags": ["bell"]}
    if enlace.startswith("https://"):
        cuerpo["click"] = enlace
    requests.post(NTFY, json=cuerpo, timeout=20).raise_for_status()


def texto_alerta(r):
    valor = radar.pesos(r["valor_cop"]) if r["valor_cop"] else "sin valor publicado"
    desc = " ".join(r["descripcion"].split())[:300]
    cierre = f" · cierra {r['fecha_cierre']}" if r.get("fecha_cierre") else ""
    return (f"Puntaje {r['puntaje']} · {valor}{cierre}\n{desc}",
            f"Santander: {r['entidad']}"[:120])


def main():
    ap = argparse.ArgumentParser(description="Vigilante de licitaciones de Santander")
    ap.add_argument("--sin-avisar", action="store_true", help="solo muestra lo que avisaria")
    args = ap.parse_args()
    tema = os.environ.get("NTFY_TOPIC", "").strip()
    if not tema and not args.sin_avisar:
        sys.exit("Falta NTFY_TOPIC (el tema de ntfy). Use --sin-avisar para probar sin avisar.")

    encontradas = alertas_de_santander()
    vistos = leer_vistos()
    primera_vez = vistos is None
    vistos = vistos or set()
    nuevas = [r for r in encontradas if r["id"] not in vistos]
    print(f"{len(encontradas)} alertas de Santander en {DIAS} dias; {len(nuevas)} nuevas"
          + (" (primera vez: se toman como punto de partida)" if primera_vez else ""))

    if not args.sin_avisar:
        if primera_vez:
            avisar(tema, "Vigilante activo",
                   f"Busco en SECOP cada 30 minutos y le aviso de licitaciones nuevas de Santander. "
                   f"Hoy hay {len(encontradas)} en los ultimos {DIAS} dias; esas no se avisan.", prioridad=2)
        else:
            for r in nuevas[:MAX_AVISOS]:
                mensaje, titulo = texto_alerta(r)
                avisar(tema, titulo, mensaje, r["url"])
            if len(nuevas) > MAX_AVISOS:
                avisar(tema, f"Santander: {len(nuevas) - MAX_AVISOS} licitaciones nuevas mas",
                       "Abra el panel para verlas.")
    else:
        for r in nuevas[:MAX_AVISOS]:
            print(" -", texto_alerta(r)[1], "|", texto_alerta(r)[0].splitlines()[0])

    guardar_vistos(vistos | {r["id"] for r in encontradas})


if __name__ == "__main__":
    main()
