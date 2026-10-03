// Web compartida: no hay servidor. Los datos son archivos cifrados (AES-256-GCM, clave derivada de la
// contrasena con PBKDF2) que se descifran aqui, en el navegador. La pagina original sigue pidiendo
// "/api/..." y este codigo le responde con esos archivos, asi no hay que reescribirla.
(function () {
  'use strict';
  const fetchReal = window.fetch.bind(window);
  const ITERACIONES = 600000;
  let clave = null, abrir;
  const listo = new Promise(r => { abrir = r; });
  const aBytes = (b64) => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const aB64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));

  async function derivar(contrasena, salB64) {
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(contrasena), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({ name: 'PBKDF2', salt: aBytes(salB64), iterations: ITERACIONES, hash: 'SHA-256' },
      base, { name: 'AES-GCM', length: 256 }, true, ['decrypt']);
  }
  async function descifrar(k, buf) {
    const b = new Uint8Array(buf);
    const plano = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b.slice(0, 12) }, k, b.slice(12));
    const flujo = new Blob([plano]).stream().pipeThrough(new DecompressionStream('gzip'));
    return JSON.parse(await new Response(flujo).text());
  }
  async function archivo(nombre) {
    const r = await fetchReal('data/' + nombre + '?m=' + Math.floor(Date.now() / 60000), { cache: 'no-store' });
    return r.ok ? r.arrayBuffer() : null;
  }
  const json = (obj, estado = 200) => new Response(JSON.stringify(obj), { status: estado, headers: { 'Content-Type': 'application/json' } });

  window.fetch = async function (entrada, opciones) {
    const url = typeof entrada === 'string' ? entrada : entrada.url;
    if (!url.startsWith('/api/')) return fetchReal(entrada, opciones);
    await listo;
    const u = new URL(url, location.href);
    const ruta = u.pathname;
    if (ruta === '/api/notificaciones') return json({ items: [], sin_leer: 0, intervalo_min: 60 });
    if (ruta === '/api/pendientes') return json([]);
    const nombres = { '/api/vencimientos': 'vencimientos', '/api/mercado': 'mercado', '/api/criterios': 'criterios' };
    const nombre = ruta === '/api/alertas' ? 'alertas_' + (u.searchParams.get('dias') || '7') : nombres[ruta];
    if (!nombre) return json({ error: 'No disponible en la web compartida.' }, 404);
    try {
      const buf = await archivo(nombre + '.enc');
      if (!buf) return json({ error: 'Este periodo todavía no está disponible. Pruebe con uno más corto.' }, 503);
      return json(await descifrar(clave, buf));
    } catch (_) { return json({ error: 'No se pudieron leer los datos. Recargue la página.' }, 500); }
  };

  async function probar(k) {
    const buf = await archivo('check.enc');
    if (!buf) throw new Error('sin datos');
    return (await descifrar(k, buf)).ok === true;
  }
  async function entrarCon(k, recordar) {
    clave = k;
    const exportada = aB64(await crypto.subtle.exportKey('raw', k));
    try { (recordar ? localStorage : sessionStorage).setItem('radar-clave', exportada); } catch (_) {}
    document.getElementById('acceso').hidden = true;
    abrir();
  }
  async function claveGuardada() {
    for (const almacen of [sessionStorage, localStorage]) {
      try {
        const g = almacen.getItem('radar-clave'); if (!g) continue;
        const k = await crypto.subtle.importKey('raw', aBytes(g), { name: 'AES-GCM' }, true, ['decrypt']);
        if (await probar(k)) return k;
        almacen.removeItem('radar-clave');
      } catch (_) { try { almacen.removeItem('radar-clave'); } catch (__) {} }
    }
    return null;
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const caja = document.getElementById('acceso'), form = document.getElementById('acceso-form');
    const campo = document.getElementById('acceso-clave'), error = document.getElementById('acceso-error');
    const boton = document.getElementById('acceso-entrar');
    const guardada = await claveGuardada();
    if (guardada) { clave = guardada; caja.hidden = true; abrir(); return; }
    campo.focus();
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      error.hidden = true; boton.disabled = true; boton.textContent = 'Comprobando…';
      try {
        const sal = (await (await fetchReal('data/salt.txt', { cache: 'no-store' })).text()).trim();
        const k = await derivar(campo.value, sal);
        let bien = false;
        try { bien = await probar(k); } catch (_) { bien = false; }
        if (!bien) throw new Error('mala');
        await entrarCon(k, document.getElementById('acceso-recordar').checked);
      } catch (_) {
        error.textContent = 'Contraseña incorrecta. Revísela e intente de nuevo.'; error.hidden = false;
        campo.select(); boton.disabled = false; boton.textContent = 'Entrar';
      }
    });
  });
})();
