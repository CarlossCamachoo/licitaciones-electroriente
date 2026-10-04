# Hoja compartida del equipo

Cada licitación que alguien marca **Me interesa** en el panel se copia como una fila en una hoja de
Google Sheets que ve todo el equipo. Si esa persona la quita o la descarta, la fila no se borra:
cambia su *Estado*. Las columnas *Seguimiento* y *Comentarios* son del equipo y el radar nunca las toca.

## Cómo funciona

- El panel (en el Mac) envía el aviso a su propio servidor y este lo reenvía a un script de Google
  (Apps Script) que escribe en la hoja. La dirección y la clave del script viven solo en
  `config/hoja.yaml`, que está fuera de git.
- Cada persona escribe su nombre la primera vez que marca algo. Se guarda en su navegador.
- Si no hay conexión, el aviso espera en una cola y se reintenta cada minuto.
- La web compartida (con contraseña) también escribe en la hoja: ver «Web compartida».

## Instalación (una sola vez)

1. Cree una hoja nueva en <https://sheets.new> y póngale un nombre, por ejemplo «Licitaciones del equipo».
2. En la hoja: **Extensiones → Apps Script** (o un proyecto nuevo en script.google.com, poniendo el ID de la
   hoja en `ID_LIBRO`). Borre lo que haya y pegue el código de `app/hoja_equipo.gs` con la clave puesta
   (la copia lista está en `config/hoja_equipo.gs`, fuera de git). Antes de implementar, ejecute `doGet`
   una vez desde el editor para que Google pida los permisos.
3. **Implementar → Nueva implementación → Aplicación web**. Ejecutar como: *Yo*. Quién tiene acceso:
   *Cualquier persona*. Autorice los permisos que pide Google y copie la dirección que termina en `/exec`.
4. Pegue esa dirección en `url:` de `config/hoja.yaml`.
5. Comparta la hoja con el equipo (botón **Compartir**, con sus correos). Pueden editarla.
6. Abra la app del Mac: se reinicia sola y desde ese momento cada «Me interesa» llega a la hoja.

Abrir la dirección `/exec` en el navegador debe mostrar «La hoja del radar está activa».

## Si se cambia el código del script

Hay que crear una **nueva versión** en *Implementar → Administrar implementaciones → Editar → Nueva versión*.
La dirección no cambia.

## Web compartida

La web compartida escribe en la misma hoja. Para eso su dirección y clave viajan **cifradas con la
contraseña de la web** (archivo `data/hoja.enc`, que sale de los secretos de GitHub `HOJA_URL` y
`HOJA_TOKEN`). Autorizado por el dueño del proyecto.

El riesgo es que quien tenga la contraseña de la web puede sacar esa clave y escribir en la hoja. Está
acotado así: el script solo acepta ids de proceso reales de SECOP (`CO1.XXX.123456`), enlaces de
`community.secop.gov.co`, estados válidos, y no más de 120 escrituras por hora; la clave no da lectura
de la hoja ni acceso a la cuenta de Google; y la hoja guarda historial de versiones.

Si cambia la contraseña de la web, cambia el cifrado y quien ya no deba tener acceso lo pierde. Si
sospecha de un uso indebido, cambie la clave: genere una nueva, edite `TOKEN` en el script de Google,
publique una versión nueva y actualice los secretos (`gh secret set HOJA_TOKEN`) y `config/hoja.yaml`.

## Usuarios: quién marca cada licitación

Cada persona entra a la web compartida con **su usuario y su contraseña**, y el nombre sale de ahí: ya no
se le pregunta al marcar un «Me interesa». El panel del Mac usa el nombre de `persona:` en `config/hoja.yaml`.

Cómo funciona: la clave de los datos se guarda cifrada una vez por persona (una «ranura», en
`data/usuarios.json`), cada una abierta solo con su contraseña. Nadie recibe la contraseña maestra
(`CLAVE_WEB`), que ya no sirve para entrar: es un valor al azar que nadie conoce ni necesita guardar.

Se gestionan con `src/usuarios_web.py` (no hace falta el entorno del proyecto, solo `python3` y `gh`):

```bash
python3 src/usuarios_web.py listar
python3 src/usuarios_web.py agregar "Ana Pérez"      # crea el usuario «ana» y su contraseña
python3 src/usuarios_web.py clave ana                # contraseña nueva
python3 src/usuarios_web.py quitar ana
```

La lista vive en `config/usuarios.txt` (fuera de git; GitHub no deja leer un secreto una vez guardado).
Cada cambio la sube como secreto `USUARIOS_WEB` y publica la web en unos 3 minutos.

Si alguien se va, `quitar` impide que entre de nuevo, pero ya conoce la clave de los datos. Para cortar
del todo, cambie también `CLAVE_WEB` por otro valor al azar (`gh secret set CLAVE_WEB`) y publique: como
nadie la usa para entrar, no hay que avisar a nadie.

## Aviso de versión nueva

La web compara su versión con `version.txt` al volver a la pestaña y cada 5 minutos. Si hay una nueva,
muestra «Hay una versión nueva de la web» con un botón Actualizar.

## Publicar la web al instante y con puntualidad

El mismo script de la hoja hace de intermediario para pedir a GitHub que publique la web:
- **Botón «Actualizar» en la web compartida:** pide una publicación nueva (como mucho una cada 3 minutos) y
  espera 1 o 2 minutos a que aparezcan los datos nuevos, sin recargar.
- **Disparador cada 30 minutos** (`publicarProgramado`, de 6 a. m. a 10 p. m. hora de Colombia): es más
  puntual que el horario de GitHub, que a veces se retrasa casi una hora. El horario de GitHub queda de respaldo.

Necesita un token de GitHub que solo pueda lanzar tareas de este repositorio (fine-grained, permiso
*Actions: Read and write*, nada más). Se guarda **solo** en las propiedades del script de Google
(Configuración del proyecto → Propiedades de la secuencia de comandos → `GH_TOKEN`), nunca en la web ni en el repositorio.
El disparador se crea en el editor del script, página **Activadores → Agregar activador**: función
`publicarProgramado`, implementación «Encabezado», fuente «Basado en el tiempo», «Cronómetro por minuto»,
«Cada 30 minutos». (La función `instalarDisparador` hace lo mismo por código, pero el selector de funciones
del editor a veces ejecuta otra función sin avisar; en la página Ejecuciones se ve cuál corrió.)

El token vence (máximo un año): al vencer, el botón sigue funcionando leyendo lo ya publicado; se renueva
creando otro y cambiando la propiedad.

## Lo que marcó el equipo, en cada tarjeta

La web lee de la hoja un resumen corto (quién la marcó y su Seguimiento; nunca el objeto ni el valor) y lo
muestra en cada tarjeta: «Ana la marcó · Preparando oferta», o «Usted y Ana la marcaron». Si dos personas marcan
la misma licitación, los nombres se suman en la hoja («Ana, Carlos»). Hay un filtro **Equipo** (marcadas por el
equipo / que nadie ha marcado). Se actualiza al abrir, al volver a la pestaña, cada 3 minutos y al marcar algo.
El resumen se guarda 30 segundos en la memoria del script para no leer la hoja en cada consulta.
Muestra los «Me interesa» (con su Seguimiento) y también los «Descartar»: estos viven en la pestaña «Descartadas» de la misma hoja (fecha, persona, entidad, objeto, id) y en la tarjeta aparece «Ana la descartó». Si la persona se arrepiente, su nombre sale de esa pestaña y, si ya nadie la descarta, la fila se borra.


## Pestaña «En trámite» (seguimiento del equipo)

La web tiene una pestaña **En trámite** con las licitaciones que alguien marcó «Me interesa», ordenadas por la
fecha de cierre más cercana. Cada una muestra su etapa (Por estudiar, Preparando oferta, Presentada, Ganada,
Perdida, Descartada), las notas del equipo, el valor, quién la marcó y el enlace a SECOP. Se cambia la etapa y se
escriben notas desde la propia web: se guardan en las columnas **Seguimiento** y **Comentarios** de la hoja, así
que el equipo puede seguir editándolas en Excel o en Google Sheets. Es compartido: la última persona que cambia
algo manda. Un aviso en la parte de arriba cuenta las que cierran en 3 días o menos y aún no se presentan.
El script lo hace con la acción `seguimiento` (valida el id, la etapa y limita el largo de las notas).
