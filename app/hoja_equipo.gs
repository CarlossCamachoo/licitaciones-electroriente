// Hoja compartida del equipo para el Radar de Licitaciones de Electroriente.
//
// Recibe cada licitacion que alguien marca «Me interesa» en el radar y la copia como una fila.
// Si esa persona la quita o la descarta, la fila no se borra: cambia su Estado.
// Las columnas Seguimiento y Comentarios son del equipo; el radar nunca las toca.
//
// Instalacion (una sola vez): ver docs/HOJA_EQUIPO.md. Reemplace __TOKEN__ por la clave que se le entrego.

const TOKEN = '__TOKEN__';
const ID_LIBRO = '__ID_LIBRO__';   // vacio si el script se creo desde la propia hoja (Extensiones > Apps Script)
const NOMBRE_HOJA = 'Me interesan';
const COLUMNAS = ['Fecha', 'Persona', 'Estado', 'Entidad', 'Objeto', 'Valor (COP)', 'Cierre', 'Puntaje',
  'Factibilidad', 'Departamento', 'Modalidad', 'Tipo de contrato', 'Enlace', 'Id del proceso',
  'Seguimiento', 'Comentarios'];
const N_RADAR = 14;   // las primeras 14 columnas las escribe el radar
const COL = (nombre) => COLUMNAS.indexOf(nombre) + 1;
const SEGUIMIENTO = ['Por estudiar', 'Preparando oferta', 'Presentada', 'Ganada', 'Perdida', 'Descartada'];

// Validaciones: la clave puede estar en manos de todo el equipo, asi que el script solo acepta lo que
// parece una licitacion real de SECOP y limita cuantas filas se pueden escribir por hora.
const ID_VALIDO = /^CO1\.[A-Z0-9]+\.\d{3,12}$/;
const ENLACE_VALIDO = /^https:\/\/community\.secop\.gov\.co\//;
const ESTADOS = ['interesa', 'descarta', ''];
const FACTIBILIDAD = ['Alta', 'Media', 'Por revisar'];
const MAX_POR_HORA = 120;

function hoja_() {
  const libro = ID_LIBRO ? SpreadsheetApp.openById(ID_LIBRO) : SpreadsheetApp.getActiveSpreadsheet();
  let h = libro.getSheetByName(NOMBRE_HOJA);
  if (!h) { h = libro.getSheets()[0]; h.setName(NOMBRE_HOJA); }
  if (h.getLastRow() === 0) {
    h.getRange(1, 1, 1, COLUMNAS.length).setValues([COLUMNAS])
      .setFontWeight('bold').setBackground('#000775').setFontColor('#FFFFFF').setVerticalAlignment('middle');
    h.setFrozenRows(1);
    const anchos = [130, 110, 150, 240, 420, 130, 100, 70, 100, 130, 200, 150, 120, 150, 150, 300];
    anchos.forEach((a, i) => h.setColumnWidth(i + 1, a));
    h.getRange(2, COL('Valor (COP)'), 998, 1).setNumberFormat('$#,##0');
    h.getRange(2, COL('Objeto'), 998, 1).setWrap(true);
    h.getRange(2, COL('Comentarios'), 998, 1).setWrap(true);
    h.getRange(2, COL('Seguimiento'), 998, 1).setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInList(SEGUIMIENTO, true).setAllowInvalid(true).build());
  }
  return h;
}

function salida_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// Un texto que empiece por = + - @ se tomaria como formula: se le antepone un espacio.
function texto_(valor, largo) {
  const t = String(valor == null ? '' : valor).replace(/\s+/g, ' ').trim().slice(0, largo || 300);
  return /^[=+\-@]/.test(t) ? ' ' + t : t;
}

function dentroDelLimite_() {
  const cache = CacheService.getScriptCache();
  const clave = 'n_' + Utilities.formatDate(new Date(), 'UTC', 'yyyyMMddHH');
  const n = Number(cache.get(clave) || 0) + 1;
  cache.put(clave, String(n), 3700);
  return n <= MAX_POR_HORA;
}

// Abrir la direccion publicada en el navegador comprueba que la hoja esta activa.
function doGet() {
  hoja_();
  return salida_({ ok: true, mensaje: 'La hoja del radar está activa.' });
}

function doPost(e) {
  const cerrojo = LockService.getScriptLock();
  try {
    cerrojo.waitLock(20000);
    const d = JSON.parse(e.postData.contents);
    if (d.token !== TOKEN) return salida_({ ok: false, error: 'clave' });
    if (!ID_VALIDO.test(String(d.id || ''))) return salida_({ ok: false, error: 'id no valido' });
    const estado = d.estado == null ? '' : String(d.estado);
    if (ESTADOS.indexOf(estado) < 0) return salida_({ ok: false, error: 'estado no valido' });
    if (!dentroDelLimite_()) return salida_({ ok: false, error: 'demasiadas solicitudes' });
    const h = hoja_();
    const id = texto_(d.id, 120);
    const filas = Math.max(h.getLastRow() - 1, 0);
    const ids = filas ? h.getRange(2, COL('Id del proceso'), filas, 1).getValues().map(f => String(f[0])) : [];
    const i = ids.indexOf(id);
    const ahora = Utilities.formatDate(new Date(), 'America/Bogota', 'yyyy-MM-dd HH:mm');
    const persona = texto_(d.persona, 60);

    if (estado === 'interesa') {
      const url = String(d.url || '');
      const valor = Number(d.valor);
      const puntaje = Math.min(100, Math.max(0, Number(d.puntaje) || 0));
      const factibilidad = FACTIBILIDAD.indexOf(String(d.factibilidad)) >= 0 ? String(d.factibilidad) : '';
      const fila = [ahora, persona, 'Me interesa', texto_(d.entidad, 200), texto_(d.objeto, 600),
        valor > 0 && valor < 1e13 ? valor : '', texto_(d.cierre, 20), puntaje, factibilidad,
        texto_(d.departamento, 60), texto_(d.modalidad, 80), texto_(d.tipo, 60), '', id];
      let n;
      if (i >= 0) {
        n = i + 2;
        h.getRange(n, 1, 1, N_RADAR).setValues([fila]);
      } else {
        n = h.getLastRow() + 1;
        h.getRange(n, 1, 1, N_RADAR).setValues([fila]);
        h.getRange(n, COL('Seguimiento')).setValue('Por estudiar');
      }
      // Enlace como texto enriquecido (no como formula): funciona igual en cualquier idioma de la hoja.
      if (ENLACE_VALIDO.test(url)) {
        h.getRange(n, COL('Enlace')).setRichTextValue(
          SpreadsheetApp.newRichTextValue().setText('Abrir en SECOP').setLinkUrl(url).build());
      }
    } else if (i >= 0) {
      // La quitaron o la descartaron: la fila se conserva y cambia su estado.
      const que = estado === 'descarta' ? 'Descartada' : 'Quitada';
      h.getRange(i + 2, COL('Fecha'), 1, 1).setValue(ahora);
      h.getRange(i + 2, COL('Estado'), 1, 1).setValue(que + (persona ? ' por ' + persona : ''));
    }
    return salida_({ ok: true });
  } catch (err) {
    return salida_({ ok: false, error: String(err) });
  } finally {
    cerrojo.releaseLock();
  }
}
