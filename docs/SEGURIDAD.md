# Auditoria de seguridad (2 oct 2026)

Alcance: radar.py y config. Es una herramienta de linea de comandos sin
login, base de datos, servidor ni subida de archivos. De los 28 puntos de la
lista, aplican los de secretos, validacion de entradas, logs y dependencias.

| Punto | Estado | Evidencia |
|---|---|---|
| 1 Sin claves en el codigo | OK | Busqueda de patrones sin hallazgos |
| 2 .env en .gitignore | OK | `.gitignore` creado. Sin historial git todavia |
| 3-11, 12-16, 22-25 (auth, BD, API propia) | No aplica | No hay servidor ni usuarios |
| 17-18 Datos sensibles y logs | OK | No se registran credenciales. `docs/empresa/` esta en .gitignore |
| 19-20 Validacion de entradas | OK | `limpiar()` quita caracteres de control de lo que llega de la API; `url_segura()` solo acepta https |
| 21 Subida de archivos | No aplica | |
| 26 Errores y HTTPS | OK | Solo se consulta por https; los errores de red no muestran trazas |
| YAML | OK | Solo `yaml.safe_load` |
| 27 Escaneo de dependencias | OK | `pip-audit` sin hallazgos (3 oct 2026). El entorno `.venv` usa Python 3.12 con requests 2.34 y urllib3 2.8 |
| 28 Dependencias al dia | OK | Dependabot y deteccion de secretos activos en el repositorio. Para actualizar: `uv pip install --python .venv/bin/python -U -r requirements-publicar.txt` |

## Si un dia se agrega token de SECOP
Usar la variable de entorno `SOCRATA_APP_TOKEN` (ya soportada, opcional).
Nunca escribirla en el codigo ni en config/. Si se filtra, regenerarla.

## Antes de subir a GitHub
Repositorio **privado**. Los documentos de la empresa (RUP, RUT, estados
financieros) van en `docs/empresa/`, que ya esta ignorado por git.
