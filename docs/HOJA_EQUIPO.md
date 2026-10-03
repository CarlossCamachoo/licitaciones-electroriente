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
- La web compartida (con contraseña) **todavía no** escribe en la hoja: ver «Pendiente».

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

## Pendiente

Que la web compartida también escriba en la hoja exige poner la dirección y la clave de la hoja dentro
de la web pública (cifradas con la contraseña del equipo). Está sin hacer a propósito: es una decisión
de seguridad que debe tomar el dueño del proyecto.
