# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Carlos, que trabaja en Electroriente S.A.S. y viene de marketing digital y automatización, no de contratación pública. Es su primera vez licitando. Lo usa junto con el área de licitaciones de la empresa. Desde un computador (el panel no se piensa para celular).

Su trabajo principal con el panel, cada día: decidir rápido a qué licitaciones vale la pena aplicar, revisando las alertas de la más a la menos factible y descartando o apartando para estudiar.

Otros trabajos que también hace: calibrar la búsqueda (revisar ruido, agregar o quitar términos) y reunir los documentos de la empresa para poder presentarse.

## Product Purpose
Acompañar el ciclo de una licitación pública para Electroriente, desde detectar la oportunidad en SECOP II hasta, más adelante, liquidar el contrato. Hoy cubre detectar y puntuar procesos, ver qué documentos de la empresa faltan para aplicar y explicar los criterios con los que se decide.

Dos trabajos a la vez: buscar oportunidades y enseñar el proceso mientras se usa. Las explicaciones importan tanto como el código. Éxito: que el área confíe en las alertas porque puede rastrear por qué entró cada una, y que Carlos aprenda a licitar usándolo.

## Positioning
Es un radar hecho a la medida de una distribuidora de material eléctrico y automatización industrial que suministra y asesora, pero instala a través de aliados. Cada resultado explica por qué entró ("Coincide por"), separa lo que puede suministrar de lo que requiere unión temporal, y muestra qué documentos faltan. Un buscador genérico de SECOP no conoce esas reglas del negocio.

## Operating Context
- Fuente de datos: datos abiertos de SECOP II (Socrata), sin llave de API. Hasta unos 220.000 procesos en 90 días; la primera consulta tarda de segundos a un par de minutos.
- Se filtra y puntúa en local con reglas editables en archivos de configuración (`config/filtros.yaml`, `perfil.yaml`, `criterios.yaml`, `documentos.yaml`).
- El panel es un servidor local en Python que escucha solo en 127.0.0.1.
- Los documentos de la empresa se suben al panel y se guardan en el computador (`docs/empresa/`, fuera de git).
- La herramienta no interpreta derecho contractual; prepara para hablar con un abogado, no lo reemplaza.
- Interfaz en español colombiano.

## Capabilities and Constraints
- Hoy: radar con puntaje y niveles de factibilidad, vistas Radar y Por revisar, filtro de puntaje, periodos de 3 a 90 días, subida de documentos de la empresa, cruce de documentos faltantes por alerta y pestaña de criterios.
- No construido: lectura de pliegos, extracción de requisitos y plazos, y lectura del contenido de los documentos subidos.
- La fecha de cierre de ofertas no viene en los datos abiertos de SECOP. Los códigos UNSPSC no son confiables en esos datos.
- Pendientes bloqueantes: RUP vigente con códigos UNSPSC y validar el rango de cuantía. El mínimo de cuantía es 5 millones, decidido por el área; el resto del rango es un supuesto.
- Sin documentos de la empresa aún: lo que dependa de ellos sigue sin construir a propósito.
- Plataformas privadas (Suplos, SAP Ariba, Par Service, Te Cuento de EPM) fuera de alcance.
- Sin decidir: cómo se comparte con el área. La intención declarada es compartirlo desde el dominio de GitHub de Carlos. Hoy el panel es un servidor Python que consulta SECOP y guarda archivos de la empresa, así que no es un sitio estático. Queda abierto dónde se alojaría y con qué control de acceso, y los documentos de la empresa no deben quedar en un sitio público.

## Brand Commitments
El panel debe seguir la identidad de la web de la empresa (https://www.electroriente.com.co/home), indicada por el usuario: azul marino (#011E91 para botones y títulos, #000775 para la barra superior), texto casi negro (#212529), fondo blanco, tipografía DM Sans y botones en forma de píldora. El panel usa solo esa familia tipográfica porque es la de la marca.

El logo (versión clara, blanco sobre azul marino) se descargó de la web de la empresa a `web/logo.webp` con autorización del usuario, y se usa en la barra superior. Solo se conserva la versión clara. No hay manual de marca. No inventar variantes del logo.

## Evidence on Hand
- Datos reales de SECOP II consultados en vivo (octubre de 2026).
- Perfil de la empresa y catálogo de la tienda en línea reflejados en `config/perfil.yaml`.
- Sin historial confirmado de contratación estatal directa: la herramienta abre un canal nuevo, no optimiza uno existente.
- Paleta, tipografía y logo (versión clara) tomados de la web de la empresa. No hay manual de marca, testimonios ni documentos de la empresa en el repositorio.

## Product Principles
1. Cada alerta debe poder explicarse: si el área no puede rastrear por qué salió algo, deja de confiar en la herramienta.
2. Mostrar lo dudoso en lugar de esconderlo: lo que no encaja del todo va a "Por revisar", no se pierde.
3. Enseñar mientras se usa: lenguaje claro para alguien que licita por primera vez, sin jerga innecesaria.
4. No fingir certeza que los datos no dan: las estimaciones se marcan como estimaciones y los supuestos como supuestos.
5. Los datos de la empresa se quedan bajo su control.

## Accessibility & Inclusion
Sin requisito específico declarado por el equipo. Se aplican buenas prácticas generales de contraste y teclado.
