#!/usr/bin/env python3
"""
Vigilante en la nube: busca en SECOP y avisa por correo de las licitaciones
nuevas de Santander, aunque el computador este apagado.

Lo ejecuta GitHub Actions cada 30 minutos (ver .github/workflows/vigilante.yml).
Tambien se puede probar a mano:

    python src/vigilante_nube.py --sin-avisar                   # solo muestra lo que avisaria

El aviso es una "issue" (un tema) que se crea en el repositorio de GitHub por cada
licitacion nueva. GitHub manda un correo por cada issue nueva a quien sigue el
repositorio (el dueño lo sigue por defecto) y tambien la muestra en su campana de
GitHub. No hace falta configurar correo, contraseñas ni aplicaciones: solo usa el
permiso que GitHub le da a cada ejecucion (GITHUB_TOKEN).

Que cuenta como "nueva": una alerta (factibilidad alta o media) de una entidad
del departamento de Santander cuyo id no esta en data/vistos_nube.json. Ese
archivo lo conserva GitHub entre ejecuciones (cache). La primera vez no avisa de
lo que ya existe: solo crea una issue "Vigilante activo" para confirmar que el aviso llega.
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
API = "https://api.github.com"
ETIQUETA = "licitacion-santander"


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


def avisar(titulo, cuerpo):
    """Crea una issue en el repositorio: GitHub la manda por correo."""
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    r = requests.post(f"{API}/repos/{repo}/issues", timeout=20,
                      headers={"Authorization": f"Bearer {token}",
                               "Accept": "application/vnd.github+json"},
                      json={"title": titulo[:200], "body": cuerpo, "labels": [ETIQUETA]})
    r.raise_for_status()


def texto_alerta(r):
    """(titulo, cuerpo en markdown) de una alerta."""
    valor = radar.pesos(r["valor_cop"]) if r["valor_cop"] else "sin valor publicado"
    desc = " ".join(r["descripcion"].split())[:600]
    lineas = [f"**{r['entidad']}** · {r['departamento']}", "",
              f"- Puntaje: **{r['puntaje']}** ({'factibilidad ' + r['nivel']})",
              f"- Valor: {valor}",
              f"- Publicado: {r['fecha_publicacion']}"]
    if r.get("fecha_cierre"):
        lineas.append(f"- Cierre: {r['fecha_cierre']}")
    if r["coincidencias"]:
        lineas.append("- Coincide por: " + ", ".join(r["coincidencias"][:8]))
    lineas += ["", desc, ""]
    if r["url"]:
        lineas.append(f"[Abrir en SECOP]({r['url']})")
    return f"Santander: {r['entidad']} · {valor}", "\n".join(lineas)


def main():
    ap = argparse.ArgumentParser(description="Vigilante de licitaciones de Santander")
    ap.add_argument("--sin-avisar", action="store_true", help="solo muestra lo que avisaria")
    args = ap.parse_args()
    if not args.sin_avisar and not (os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY")):
        sys.exit("Faltan GITHUB_TOKEN y GITHUB_REPOSITORY (los da GitHub Actions). Use --sin-avisar para probar.")

    encontradas = alertas_de_santander()
    vistos = leer_vistos()
    primera_vez = vistos is None
    vistos = vistos or set()
    nuevas = [r for r in encontradas if r["id"] not in vistos]
    print(f"{len(encontradas)} alertas de Santander en {DIAS} dias; {len(nuevas)} nuevas"
          + (" (primera vez: se toman como punto de partida)" if primera_vez else ""))

    if not args.sin_avisar:
        if primera_vez:
            avisar("Vigilante activo: avisará de licitaciones nuevas de Santander",
                   f"Busco en SECOP cada 30 minutos (6:00 a 20:59, hora de Colombia) y creo una issue por cada "
                   f"licitación nueva de Santander; GitHub se la envía por correo.\n\n"
                   f"Hoy hay {len(encontradas)} alertas de Santander en los últimos {DIAS} días; esas no se avisan.")
        else:
            for r in nuevas[:MAX_AVISOS]:
                titulo, cuerpo = texto_alerta(r)
                avisar(titulo, cuerpo)
            if len(nuevas) > MAX_AVISOS:
                avisar(f"Santander: {len(nuevas) - MAX_AVISOS} licitaciones nuevas más",
                       "Abra el panel para verlas.")
    else:
        for r in nuevas[:MAX_AVISOS]:
            print(" -", texto_alerta(r)[0])

    guardar_vistos(vistos | {r["id"] for r in encontradas})


if __name__ == "__main__":
    main()
