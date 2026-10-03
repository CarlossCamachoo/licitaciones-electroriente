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
