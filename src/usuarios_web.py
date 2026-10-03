#!/usr/bin/env python3
"""
Usuarios de la web compartida: cada persona entra con su usuario y su contrasena, y asi la hoja del
equipo sabe quien marco cada licitacion sin preguntarle el nombre.

    python3 src/usuarios_web.py listar
    python3 src/usuarios_web.py agregar "Ana Pérez"            # crea usuario «ana» y una contrasena
    python3 src/usuarios_web.py agregar "Ana Pérez" --usuario aperez
    python3 src/usuarios_web.py clave ana                       # contrasena nueva para ana
    python3 src/usuarios_web.py quitar ana
    python3 src/usuarios_web.py publicar                        # solo sincronizar y publicar

La lista vive en config/usuarios.txt (fuera de git; una linea por persona: usuario|Nombre|contrasena).
GitHub no deja leer un secreto una vez guardado, asi que ese archivo es la fuente: cada cambio lo sube
completo como secreto USUARIOS_WEB y lanza la publicacion de la web (unos 3 minutos).
Solo usa la libreria estandar y el comando `gh`.
"""

import argparse
import re
import secrets
import subprocess
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "config" / "usuarios.txt"
REPO = "CarlossCamachoo/licitaciones-electroriente"
CONSONANTES, VOCALES = "bdfgklmnprstvz", "aeiou"


def normalizar(texto):
    t = unicodedata.normalize("NFD", texto.strip().lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def contrasena_nueva():
    """Cuatro «palabras» pronunciables y dos digitos: facil de dictar, imposible de adivinar."""
    palabra = lambda: "".join(secrets.choice(CONSONANTES) + secrets.choice(VOCALES) for _ in range(3))
    return "-".join(palabra() for _ in range(4)) + f"-{secrets.randbelow(90) + 10}"


def leer():
    usuarios = []
    if ARCHIVO.exists():
        for linea in ARCHIVO.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#"):
                usuario, nombre, clave = linea.split("|", 2)
                usuarios.append([usuario, nombre, clave])
    return usuarios


def guardar(usuarios):
    ARCHIVO.parent.mkdir(exist_ok=True)
    cuerpo = "# usuario|Nombre|contrasena  (fuera de git; lo gestiona src/usuarios_web.py)\n"
    cuerpo += "".join(f"{u}|{n}|{c}\n" for u, n, c in usuarios)
    ARCHIVO.write_text(cuerpo, encoding="utf-8")
    ARCHIVO.chmod(0o600)


def publicar():
    cuerpo = ARCHIVO.read_text(encoding="utf-8") if ARCHIVO.exists() else ""
    r = subprocess.run(["gh", "secret", "set", "USUARIOS_WEB", "--repo", REPO], input=cuerpo, text=True)
    if r.returncode:
        sys.exit("No se pudo guardar el secreto USUARIOS_WEB. ¿Esta iniciada la sesion de gh?")
    r = subprocess.run(["gh", "workflow", "run", "publicar.yml", "--repo", REPO])
    if r.returncode:
        sys.exit("El secreto se guardo, pero no se pudo lanzar la publicacion.")
    print("Listo: la web se actualiza en unos 3 minutos.")


def buscar(usuarios, usuario):
    u = normalizar(usuario)
    for fila in usuarios:
        if fila[0] == u:
            return fila
    sys.exit(f"No existe el usuario «{u}». Use `listar` para ver los que hay.")


def main():
    ap = argparse.ArgumentParser(description="Usuarios de la web compartida")
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("listar")
    p = sub.add_parser("agregar"); p.add_argument("nombre"); p.add_argument("--usuario")
    p = sub.add_parser("clave"); p.add_argument("usuario")
    p = sub.add_parser("quitar"); p.add_argument("usuario")
    sub.add_parser("publicar")
    ap.add_argument("--sin-publicar", action="store_true", help="solo cambiar el archivo local")
    args = ap.parse_args()
    usuarios = leer()

    if args.orden == "listar":
        for u, n, c in usuarios:
            print(f"{u:14} {n:30} {c}")
        print(f"\n{len(usuarios)} usuario(s) en {ARCHIVO}")
        return
    if args.orden == "publicar":
        return publicar()

    if args.orden == "agregar":
        nombre = " ".join(args.nombre.split())
        usuario = normalizar(args.usuario or nombre.split()[0])
        if not re.fullmatch(r"[a-z0-9._-]{2,30}", usuario):
            sys.exit("El usuario solo puede tener letras sin tilde, numeros, punto, guion y guion bajo (2 a 30).")
        if any(f[0] == usuario for f in usuarios):
            sys.exit(f"Ya existe el usuario «{usuario}». Use --usuario para elegir otro.")
        clave = contrasena_nueva()
        usuarios.append([usuario, nombre, clave])
        print(f"Usuario: {usuario}\nNombre:  {nombre}\nContraseña: {clave}")
    elif args.orden == "clave":
        fila = buscar(usuarios, args.usuario)
        fila[2] = contrasena_nueva()
        print(f"Usuario: {fila[0]}\nContraseña nueva: {fila[2]}")
    elif args.orden == "quitar":
        fila = buscar(usuarios, args.usuario)
        usuarios.remove(fila)
        print(f"Se quito a {fila[1]} ({fila[0]}).")
        print("Ojo: quien ya entro conoce la clave de los datos. Para cortar el acceso del todo, cambie CLAVE_WEB.")
    guardar(usuarios)
    if not args.sin_publicar:
        publicar()


if __name__ == "__main__":
    main()
