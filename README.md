# Asistente de licitaciones, Electroriente S.A.S.

Herramienta para acompañar el ciclo de una licitación pública, desde
detectar la oportunidad hasta archivar el aprendizaje.

Estado actual: **Bloque A funcionando**, el radar de oportunidades.

---

## Qué hace hoy

Consulta los datos abiertos de SECOP II, filtra los procesos que encajan con
el perfil de Electroriente, los puntúa de 0 a 100 y explica por qué entró
cada uno.

No requiere llave de API ni iniciar sesión. Los datos son públicos.

---

## Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
# Últimos 7 días
python src/radar.py

# Últimos 30 días
python src/radar.py --dias 30

# Sin conexión, con datos de prueba
python src/radar.py --demo

# Guardar el resultado
python src/radar.py --dias 15 --salida data/revision.json
```

---

## Panel visual

```bash
python src/servidor.py          # abre http://127.0.0.1:8765
python src/servidor.py --puerto 9000
```

Muestra las alertas con filtros, resumen y el aviso de pendientes. Solo
escucha en tu computador (127.0.0.1). Si el puerto está ocupado, avisa y no
arranca. Guarda el resultado 10 minutos para no saturar SECOP.

---

## Estructura

```
config/perfil.yaml      Quién es la empresa: capacidad, portafolio, territorio
config/filtros.yaml     Reglas de inclusión, exclusión y puntaje
src/radar.py            El motor
src/servidor.py         Servidor local del panel
web/index.html          El panel visual
data/                   Resultados y datos de prueba
docs/                   Guía del ciclo de licitación
```

---

## Cómo afinar el radar

El archivo que más vas a tocar es `config/filtros.yaml`. Dos reglas simples:

- **Llegó ruido** que no sirve: agrega el término a la sección `excluir`
- **Se escapó una oportunidad**: agrega el término a la sección `incluir`

Cada resultado muestra en "Coincide por" exactamente qué término lo hizo
entrar, así que siempre se puede rastrear y corregir.

Si un día no sale nada, revisa el `umbral_alerta`. Si sale demasiado,
súbelo.

---

## Cómo se puntúa

| Elemento | Puntos |
|---|---|
| Término de especialidad núcleo, como variadores | 40 |
| Catálogo principal, como material eléctrico | 30 |
| Líneas secundarias, como iluminación o solar | 25 |
| Contexto normativo, como RETIE | 10 |
| Está en territorio prioritario | +15 |
| Entidad que ya compra este material | +10 |
| Cuantía fuera de la capacidad | -40 |

Un proceso necesita 30 puntos para generar alerta.

Los grupos aportan su peso una sola vez, no por cada término encontrado.
Así un pliego repetitivo no infla su propio puntaje.

---

## Pendientes

El proyecto lleva su propio registro de pendientes en
`config/pendientes.yaml`, y el radar **muestra un aviso cada vez que lo
corres** con lo que falta. No hay que acordarse de revisarlo.

Hay ocho pendientes abiertos, dos de ellos bloqueantes:

| Criticidad | Pendiente | Qué hace falta |
|---|---|---|
| Bloqueante | RUP vigente y códigos UNSPSC inscritos | Certificado del RUP |
| Bloqueante | Validar rango de cuantía | Estados financieros o índices del RUP |
| Alta | Certificaciones de experiencia | Certificaciones firmadas por clientes |
| Alta | Carpeta de documentos base | Existencia y representación, RUT, aportes, antecedentes |
| Media | Aseguradora para garantías | Contacto y condiciones |
| Media | Usuario de SECOP II | Confirmar cuenta y quién firma |
| Media | Validar lista UNSPSC | Nada, esto se puede hacer ya |
| Baja | Decidir si se persigue obra con aliados | Una decisión, no un documento |

**Mientras haya bloqueantes abiertos**, las alertas del radar son
exploratorias. Sirven para calibrar y aprender, no para decidir a qué
presentarse.

Cuando resuelvas algo, cambia `resuelto: false` a `resuelto: true` en
`config/pendientes.yaml` y deja de aparecer en el aviso.

Para ocultar el recordatorio en una corrida puntual:

```bash
python src/radar.py --sin-avisos
```

**Recomendación aparte:** corre el radar en modo observación dos o tres
semanas antes de actuar sobre sus alertas. Sirve para afinar los filtros sin
presión de plazos.

---

## Lo que falta construir

- **Bloque B, el analista**: extraer del pliego fechas, requisitos
  habilitantes y criterios de puntaje, y producir una ficha de decisión.
- **Bloque C, el gestor**: checklist de documentos por proceso, estado de
  cada oferta, alertas de vencimiento y archivo histórico.

---

## Limitaciones conocidas

- Solo consulta SECOP II. Las plataformas privadas (Suplos, Ariba,
  Par Service, Te Cuento) requieren credenciales y quedan fuera por ahora.
- El filtrado es por texto. Un pliego redactado de forma inusual puede
  escaparse. Por eso conviene agregar filtrado por código UNSPSC.
- No lee los documentos del pliego, solo la descripción del proceso.
- Los procesos sin valor publicado no se penalizan por cuantía: se marcan
  para revisión manual.

---

## Nota sobre el historial

A octubre de 2026 no se encontró rastro confirmado de contratación estatal
directa de Electroriente en SECOP. Aparece un registro de 2024 con EPM bajo
el nombre ELECTRORIENTE, pero sin NIT definido, así que no se puede
confirmar que sea la misma empresa.

Esto significa que la herramienta abre un canal nuevo, no optimiza uno
existente. Conviene tenerlo presente al fijar expectativas con la gerencia.
