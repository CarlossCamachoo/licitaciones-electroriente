# Contexto del proyecto

Este archivo pone al dia a cualquier instancia de Claude que abra este
repositorio. Leelo antes de proponer cambios.

---

## Que es esto

Asistente de licitaciones para **Electroriente S.A.S.**, distribuidora de
material electrico y automatizacion industrial en Bucaramanga, Santander.

El objetivo final es acompanar el ciclo completo de una licitacion publica,
desde detectar la oportunidad hasta liquidar el contrato. Hoy solo existe la
primera parte.

**Quien lo usa:** Carlos, que trabaja en la empresa, mas el area de
licitaciones. Carlos viene de marketing digital y automatizacion, no de
contratacion publica. **Es su primera vez licitando.** El asistente tiene
dos trabajos a la vez: buscar oportunidades y ensenar el proceso mientras
se usa. Eso significa que las explicaciones importan tanto como el codigo.

---

## Estado

| Bloque | Que hace | Estado |
|---|---|---|
| A, radar | Detecta procesos en SECOP y los puntua | Funcionando, probado contra la API real (2 oct 2026) |
| B, analista | Extraer requisitos y plazos de los pliegos | No construido |
| C, gestor | Checklist de documentos, plazos, archivo historico | Parcial: el panel recibe los documentos de la empresa (`docs/empresa/`, fuera de git) y dice que falta para cada alerta, por reglas de `config/documentos.yaml`. No lee pliegos ni extrae datos de los archivos |

**Ya probado en vivo:** los nombres de campo de la API son correctos. Se
corrigio un bug: el limite de 2000 descartaba el 88 % de los procesos de la
semana (hay unos 17.000). Ahora pagina, avisa si se corta, y por defecto
solo muestra procesos abiertos; los cerrados se descartan.
Seguridad: ver `docs/SEGURIDAD.md`. Pendiente: Python 3.10+ por urllib3.

---

## Datos de la empresa

- NIT 890203703-0, matricula mercantil 0000001355, Camara de Comercio de Bucaramanga
- Fundada en 1972, 54 anos de trayectoria
- Ventas anuales entre 10.000 y 20.000 millones COP, patrimonio 5.416 millones
- Actividad CIIU 4663
- Gran autorretenedor de renta y gran contribuyente de ICA en Bucaramanga

**Especialidad declarada:** automatizacion industrial y variacion de
velocidad. Esto es importante y no es obvio: la pagina web los presenta de
forma amplia como distribuidora de material electrico, pero las biografias
de Instagram y Facebook apuntan a automatizacion y variadores, y tienen las
certificaciones Schneider que lo respaldan (IAD y Drive Expert). El material
electrico es el volumen; la automatizacion es el posicionamiento y el margen.

**Limitacion operativa clave:** Electroriente suministra y asesora, pero
**instala a traves de aliados**. Los procesos de obra con montaje no le
sirven solos, solo en union temporal o consorcio.

**Experiencia acreditable:** su caso de referencia mas fuerte es
agroindustria avicola con eficiencia energetica, iluminacion LED en galpones
y sistemas de control energetico.

---

## Hallazgo importante sobre el historial

A octubre de 2026 se consulto SECOP I y II en los datos abiertos buscando por
NIT y por nombre. **No hay rastro confirmado de contratacion estatal directa.**

Aparece un unico registro de mayo de 2024 con EPM, bajo el nombre
ELECTRORIENTE, por suministro de amarres de nylon, prensaestopas y soportes
adhesivos. Pero el campo de NIT viene como "No Definido", asi que no se puede
confirmar que sea la misma empresa.

**Consecuencia:** esta herramienta abre un canal nuevo, no optimiza uno
existente. No hay historial propio contra el cual calibrar los filtros, por
eso el perfil se construyo a partir del catalogo de la tienda en linea.
Tenerlo presente al fijar expectativas con la gerencia.

---

## Pendientes

El proyecto lleva su registro en `config/pendientes.yaml` y el radar imprime
un aviso en cada corrida. Hay ocho abiertos, dos bloqueantes.

**Carlos todavia no tiene los documentos de la empresa.** Los va a subir
despues. Todo lo que dependa de documentacion esta deliberadamente sin
construir, no olvidado. No propongas construirlo hasta que lleguen los
documentos, pero tampoco lo dejes caer del radar.

Los dos bloqueantes:

1. **RUP vigente y codigos UNSPSC inscritos.** Sin esto el radar puede estar
   alertando procesos a los que la empresa no puede presentarse legalmente.
2. **Rango de cuantia.** Los valores en `config/perfil.yaml` (minimo 20
   millones, maximo 2.000 millones sola) los estimo Claude a partir del
   patrimonio publico. **Son un supuesto inventado, no un dato.** Hay que
   validarlos con el area.

Dos pendientes no dependen de documentos y se pueden resolver ya: validar la
lista UNSPSC contra el buscador oficial de SECOP, y decidir si se persigue
obra con aliados.

---

## Problema conocido, mitigado en el panel

Desde las pestanas Santander y Por revisar, la obra con aliado ya no se pierde:
resta 15 puntos y cae en "por revisar" en lugar de desaparecer. La CLI sigue
usando solo el umbral de alerta. La decision de negocio sigue abierta. Texto
original del problema:

Los procesos de obra se caen por umbral antes de que se aplique la marca de
"requiere aliado". Se vio con un caso real de Cormacarena, alumbrado publico
fotovoltaico con montaje: saco 25 puntos y el umbral esta en 30, asi que
desaparecio.

No se arreglo a proposito. La solucion correcta depende de una decision de
negocio: si Electroriente quiere perseguir obra con aliados o no. Si la
respuesta es si, hay que bajar el umbral para esa categoria y generar una
lista separada.

---

## Decisiones de diseno que conviene respetar

**El filtrado se hace en local, no en el servidor.** Se descarga por fecha y
se filtra por contenido en el codigo. Es mas facil de auditar y de ajustar
que una consulta remota compleja.

**Cada resultado explica por que entro.** El campo "Coincide por" muestra el
termino exacto. Si el area no puede rastrear por que se alerto algo, deja de
confiar en la herramienta y las alertas se vuelven ruido ignorado.

**Los grupos de palabras clave aportan su peso una sola vez**, no por cada
termino encontrado. Asi un pliego repetitivo no infla su propio puntaje.

**Los procesos sin valor publicado no se penalizan por cuantia**, se marcan
para revision manual. Muchas entidades publican el valor despues.

**La busqueda de terminos es por palabra completa**, con lookahead y
lookbehind, no por fragmento. Sin eso, "ups" coincide dentro de "grupos" y
"obra" dentro de "obrar".

---

## Como afinar el radar

Casi todo el ajuste pasa por `config/filtros.yaml`:

- Llego ruido: agregar el termino a `excluir`
- Se escapo una oportunidad: agregar el termino a `incluir`
- No sale nada nunca: bajar `umbral_alerta`
- Sale demasiado: subirlo

---

## Que no debe hacer este asistente

No interpreta derecho contractual. Puede extraer requisitos, comparar contra
checklists y avisar de vencimientos, pero la lectura juridica de un contrato
estatal necesita un abogado. El asistente prepara para esa conversacion, no
la reemplaza.

---

## Fuentes de datos

- SECOP II procesos: `https://www.datos.gov.co/resource/p6dx-8zbt.json`
- SECOP II contratos: `https://www.datos.gov.co/resource/jbjy-vk9h.json`
- SECOP I procesos: `https://www.datos.gov.co/resource/f789-7hwg.json`

Son datos abiertos, no requieren llave de API. Usan Socrata, asi que
soportan `$where`, `$select`, `$q`, `$limit` y `$order`.

El buscador publico de SECOP II (`community.secop.gov.co`) tiene CAPTCHA y
solo muestra los ultimos tres meses, y su busqueda simple cubre unicamente
los campos Referencia y Descripcion. Para automatizar, usar siempre los
datos abiertos.

**Plataformas privadas fuera de alcance por ahora:** Suplos, SAP Ariba,
Par Service y Te Cuento de EPM. Requieren credenciales que Carlos no tiene.
