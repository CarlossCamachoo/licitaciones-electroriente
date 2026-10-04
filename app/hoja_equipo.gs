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
const HOJA_DESCARTES = 'Descartadas';
const COL_DESCARTES = ['Fecha', 'Persona', 'Entidad', 'Objeto', 'Id del proceso'];
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

// Pestaña «Descartadas»: quien descarto cada licitacion, para que el equipo no pierda tiempo revisandola de nuevo.
function hojaDescartes_() {
  const libro = ID_LIBRO ? SpreadsheetApp.openById(ID_LIBRO) : SpreadsheetApp.getActiveSpreadsheet();
  let h = libro.getSheetByName(HOJA_DESCARTES);
  if (!h) {
    h = libro.insertSheet(HOJA_DESCARTES);
    h.getRange(1, 1, 1, COL_DESCARTES.length).setValues([COL_DESCARTES])
      .setFontWeight('bold').setBackground('#000775').setFontColor('#FFFFFF').setVerticalAlignment('middle');
    h.setFrozenRows(1);
    [130, 140, 240, 520, 150].forEach((a, i) => h.setColumnWidth(i + 1, a));
    h.getRange(2, 4, 998, 1).setWrap(true);
  }
  return h;
}

function leerDescartes_() {
  const h = hojaDescartes_();
  const n = Math.max(h.getLastRow() - 1, 0);
  return { h, filas: n ? h.getRange(2, 1, n, COL_DESCARTES.length).getValues() : [] };
}

function nombresDe_(texto) { return String(texto || '').split(',').map(x => x.trim()).filter(Boolean); }

// Anota (o quita) a una persona en la fila de ese proceso; la fila se borra cuando ya nadie la descarta.
function marcarDescarte_(id, persona, ahora, d, quitar) {
  if (!persona) return;
  const { h, filas } = leerDescartes_();
  const i = filas.findIndex(f => String(f[4]) === id);
  const minus = (x) => x.toLowerCase();
  if (quitar) {
    if (i < 0) return;
    const resto = nombresDe_(filas[i][1]).filter(x => minus(x) !== minus(persona));
    if (resto.length) h.getRange(i + 2, 1, 1, 2).setValues([[ahora, resto.join(', ')]]);
    else h.deleteRow(i + 2);
    return;
  }
  if (i >= 0) {
    const nombres = nombresDe_(filas[i][1]);
    if (nombres.map(minus).indexOf(minus(persona)) < 0) nombres.push(persona);
    h.getRange(i + 2, 1, 1, 2).setValues([[ahora, nombres.join(', ')]]);
  } else {
    h.getRange(h.getLastRow() + 1, 1, 1, COL_DESCARTES.length)
      .setValues([[ahora, persona, texto_(d.entidad, 200), texto_(d.objeto, 600), id]]);
  }
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

// ---- Publicacion de la web --------------------------------------------------------------------
// Pide a GitHub que genere la web de nuevo (GitHub Actions, workflow_dispatch). El permiso es un token de
// GitHub solo para Actions de este repositorio; vive en las propiedades del script (Configuracion del
// proyecto > Propiedades de la secuencia de comandos > GH_TOKEN) y nunca viaja a la web.
const REPO = 'CarlossCamachoo/licitaciones-electroriente';
const FLUJO = 'publicar.yml';

function lanzarPublicacion_() {
  const t = PropertiesService.getScriptProperties().getProperty('GH_TOKEN');
  if (!t) return { ok: false, error: 'sin permiso de GitHub' };
  const r = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + '/actions/workflows/' + FLUJO + '/dispatches', {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + t, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' },
    payload: JSON.stringify({ ref: 'main' }) });
  return { ok: r.getResponseCode() === 204, codigo: r.getResponseCode() };
}

// Lo pide quien pulsa «Actualizar» en la web: como mucho una publicacion cada 3 minutos.
function actualizarWeb_() {
  const cache = CacheService.getScriptCache();
  if (cache.get('ultima_publicacion')) return { ok: true, ya: true };
  const r = lanzarPublicacion_();
  if (r.ok) cache.put('ultima_publicacion', '1', 180);
  return r;
}

// Disparador de tiempo, cada 30 minutos: publica de 6 a. m. a 10 p. m. hora de Colombia. Es mas puntual que el
// horario de GitHub, que a veces se retrasa casi una hora.
function publicarProgramado() {
  const hora = Number(Utilities.formatDate(new Date(), 'America/Bogota', 'H'));
  if (hora >= 6 && hora < 22) lanzarPublicacion_();
}

// Ejecutar una sola vez desde el editor: crea (o reemplaza) el disparador de tiempo.
function instalarDisparador() {
  ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'publicarProgramado')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('publicarProgramado').timeBased().everyMinutes(30).create();
}

// Lo que marco el equipo: un resumen corto (sin el objeto ni el valor) para mostrarlo en cada tarjeta de la web.
function equipo_() {
  const cache = CacheService.getScriptCache();
  const guardado = cache.get('equipo');
  if (guardado) return JSON.parse(guardado);
  const h = hoja_();
  const n = Math.max(h.getLastRow() - 1, 0);
  const filas = n ? h.getRange(2, 1, n, COLUMNAS.length).getValues() : [];
  const dia = (v) => v instanceof Date ? Utilities.formatDate(v, 'America/Bogota', 'yyyy-MM-dd') : String(v || '').slice(0, 10);
  const hora = (v) => v instanceof Date ? Utilities.formatDate(v, 'America/Bogota', 'yyyy-MM-dd HH:mm') : String(v);
  const lista = filas
    .filter(f => f[COL('Estado') - 1] === 'Me interesa' && f[COL('Id del proceso') - 1])
    .map(f => ({ id: String(f[COL('Id del proceso') - 1]), persona: String(f[COL('Persona') - 1]),
      seguimiento: String(f[COL('Seguimiento') - 1] || ''), fecha: hora(f[COL('Fecha') - 1]),
      entidad: String(f[COL('Entidad') - 1]), objeto: String(f[COL('Objeto') - 1]).slice(0, 400),
      valor: Number(f[COL('Valor (COP)') - 1]) || 0, cierre: dia(f[COL('Cierre') - 1]),
      comentarios: String(f[COL('Comentarios') - 1] || '') }));
  // El enlace esta guardado como texto enriquecido: se lee aparte, en la misma pasada.
  if (n) {
    const enlaces = h.getRange(2, COL('Enlace'), n, 1).getRichTextValues().map(r => r[0].getLinkUrl() || '');
    const ids = filas.map(f => String(f[COL('Id del proceso') - 1]));
    lista.forEach(x => { x.enlace = enlaces[ids.indexOf(x.id)] || ''; });
  }
  const descartes = leerDescartes_().filas
    .filter(f => f[4]).map(f => ({ id: String(f[4]), persona: String(f[1]) }));
  const r = { ok: true, filas: lista, descartes: descartes };
  try { cache.put('equipo', JSON.stringify(r), 30); } catch (err) { /* demasiado grande para la memoria: se lee cada vez */ }
  return r;
}

// Cambia la etapa o las notas de una licitacion ya marcada «Me interesa». Es del equipo: la ultima persona que cambia manda.
function seguimiento_(d) {
  const id = texto_(d.id, 120);
  if (!ID_VALIDO.test(id)) return { ok: false, error: 'id no valido' };
  if (d.campo !== 'seguimiento' && d.campo !== 'comentarios') return { ok: false, error: 'campo no valido' };
  if (d.campo === 'seguimiento' && SEGUIMIENTO.indexOf(String(d.seguimiento)) < 0) return { ok: false, error: 'etapa no valida' };
  if (!dentroDelLimite_()) return { ok: false, error: 'demasiadas solicitudes' };
  const h = hoja_();
  const filas = Math.max(h.getLastRow() - 1, 0);
  const ids = filas ? h.getRange(2, COL('Id del proceso'), filas, 1).getValues().map(f => String(f[0])) : [];
  const i = ids.indexOf(id);
  if (i < 0) return { ok: false, error: 'no esta en la hoja' };
  if (d.campo === 'seguimiento') h.getRange(i + 2, COL('Seguimiento')).setValue(String(d.seguimiento));
  else h.getRange(i + 2, COL('Comentarios')).setValue(texto_(d.comentarios, 500));
  CacheService.getScriptCache().remove('equipo');
  return { ok: true };
}

function doPost(e) {
  const cerrojo = LockService.getScriptLock();
  try {
    cerrojo.waitLock(20000);
    const d = JSON.parse(e.postData.contents);
    if (d.token !== TOKEN) return salida_({ ok: false, error: 'clave' });
    if (d.accion === 'actualizar') return salida_(actualizarWeb_());
    if (d.accion === 'equipo') return salida_(equipo_());
    if (d.accion === 'seguimiento') return salida_(seguimiento_(d));
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
    const antes = String(d.antes || '');   // lo que habia decidido esa persona: 'interesa', 'descarta' o ''

    // Si la persona tenia la licitacion descartada y ya no, se quita de la pestaña Descartadas.
    if (antes === 'descarta' && estado !== 'descarta') marcarDescarte_(id, persona, ahora, d, true);
    if (estado === 'descarta') marcarDescarte_(id, persona, ahora, d, false);

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
        // Si otra persona ya la tenia marcada, se suman los nombres («Ana, Carlos»).
        const previa = h.getRange(n, 1, 1, 3).getValues()[0];
        if (String(previa[2]) === 'Me interesa' && previa[1] && persona) {
          const nombres = String(previa[1]).split(',').map(x => x.trim()).filter(Boolean);
          if (nombres.map(x => x.toLowerCase()).indexOf(persona.toLowerCase()) < 0) nombres.push(persona);
          fila[1] = nombres.join(', ');
        }
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
    } else if (i >= 0 && antes === 'interesa') {
      // La quitaron o la descartaron: la fila se conserva y cambia su estado.
      const que = estado === 'descarta' ? 'Descartada' : 'Quitada';
      h.getRange(i + 2, COL('Fecha'), 1, 1).setValue(ahora);
      h.getRange(i + 2, COL('Estado'), 1, 1).setValue(que + (persona ? ' por ' + persona : ''));
    }
    CacheService.getScriptCache().remove('equipo');
    return salida_({ ok: true });
  } catch (err) {
    return salida_({ ok: false, error: String(err) });
  } finally {
    cerrojo.releaseLock();
  }
}
