// Web compartida: no hay servidor. Los datos son archivos cifrados (AES-256-GCM, clave derivada de la
// contrasena con PBKDF2) que se descifran aqui, en el navegador. La pagina original sigue pidiendo
// "/api/..." y este codigo le responde con esos archivos, asi no hay que reescribirla.
(function () {
  'use strict';
  const fetchReal = window.fetch.bind(window);
  const ITERACIONES = 600000;
  const INACTIVIDAD_MS = 6 * 3600 * 1000;   // pasado este tiempo sin tocar la pagina, vuelve a pedir la contrasena
  const CLAVE_ACTIVIDAD = 'radar-actividad';
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
  // Mismo calculo que src/publicar.py: el usuario se normaliza y se convierte en el nombre de su «ranura».
  const normalizarUsuario = (u) => u.trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  async function idRanura(usuario) {
    const h = await crypto.subtle.digest('SHA-256', new TextEncoder().encode('radar:' + normalizarUsuario(usuario)));
    return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 32);
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
    const nombres = { '/api/vencimientos': 'vencimientos', '/api/mercado': 'mercado', '/api/criterios': 'criterios', '/api/hoja': 'hoja' };
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
  // Cerrar sesion: olvida la clave y el nombre de este navegador y vuelve a la pantalla de acceso.
  window.radarSalir = () => { olvidarClave(); location.reload(); };

  // Ultima vez que alguien uso la pagina (se comparte entre pestañas del mismo navegador).
  function ultimaActividad() {
    try { return Number(localStorage.getItem(CLAVE_ACTIVIDAD)) || 0; } catch (_) { return 0; }
  }
  function marcarActividad() { try { localStorage.setItem(CLAVE_ACTIVIDAD, String(Date.now())); } catch (_) {} }
  function olvidarClave() {
    for (const almacen of [sessionStorage, localStorage]) {
      try { almacen.removeItem('radar-clave'); almacen.removeItem('radar-usuario'); } catch (_) {}
    }
    try { localStorage.removeItem(CLAVE_ACTIVIDAD); } catch (_) {}
  }
  const vencida = () => Date.now() - ultimaActividad() > INACTIVIDAD_MS;
  // Con la pagina abierta: se cuenta como actividad tocar, teclear o desplazarse (se anota a lo sumo cada 30 s).
  // Si pasan 6 horas sin nada, se borra la clave y se recarga para mostrar la pantalla de acceso.
  function vigilarInactividad() {
    let ultimo = 0;
    const tocar = () => { const t = Date.now(); if (t - ultimo > 30000) { ultimo = t; marcarActividad(); } };
    ['pointerdown', 'keydown', 'scroll', 'touchstart'].forEach(ev => addEventListener(ev, tocar, { passive: true, capture: true }));
    const revisar = () => { if (vencida()) { olvidarClave(); location.reload(); } };
    setInterval(revisar, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) revisar(); });
    addEventListener('focus', revisar);
    tocar();
  }
  async function entrarCon(k, recordar, nombre) {
    clave = k;
    window.RADAR_USUARIO = nombre || '';
    const exportada = aB64(await crypto.subtle.exportKey('raw', k));
    try {
      const almacen = recordar ? localStorage : sessionStorage;
      almacen.setItem('radar-clave', exportada);
      if (nombre) almacen.setItem('radar-usuario', nombre); else almacen.removeItem('radar-usuario');
    } catch (_) {}
    document.getElementById('acceso').hidden = true;
    vigilarInactividad();
    abrir();
  }
  async function claveGuardada() {
    if (vencida()) { olvidarClave(); return null; }
    for (const almacen of [sessionStorage, localStorage]) {
      try {
        const g = almacen.getItem('radar-clave'); if (!g) continue;
        const k = await crypto.subtle.importKey('raw', aBytes(g), { name: 'AES-GCM' }, true, ['decrypt']);
        if (almacen.getItem('radar-usuario') && await probar(k)) { window.RADAR_USUARIO = almacen.getItem('radar-usuario'); return k; }
        almacen.removeItem('radar-clave'); almacen.removeItem('radar-usuario');
      } catch (_) { try { almacen.removeItem('radar-clave'); almacen.removeItem('radar-usuario'); } catch (__) {} }
    }
    return null;
  }

  // Aviso de version nueva: la pagina guarda su version en una etiqueta y la compara con version.txt.
  function vigilarVersion() {
    const meta = document.querySelector('meta[name="radar-version"]');
    const actual = meta && meta.content;
    if (!actual) return;
    let avisado = false;
    const revisar = async () => {
      if (avisado) return;
      try {
        const nueva = (await (await fetchReal('version.txt?v=' + Date.now(), { cache: 'no-store' })).text()).trim();
        if (!nueva || nueva === actual || !/^[0-9a-f]{12}$/.test(nueva)) return;
        avisado = true;
        const caja = document.createElement('div');
        caja.id = 'nueva-version'; caja.setAttribute('role', 'status');
        const texto = document.createElement('span'); texto.textContent = 'Hay una versión nueva de la web.';
        const boton = document.createElement('button'); boton.type = 'button'; boton.textContent = 'Actualizar';
        // La direccion con ?v= esquiva la memoria de 10 minutos de GitHub Pages.
        boton.onclick = () => location.replace(location.pathname + '?v=' + nueva + location.hash);
        caja.append(texto, boton); document.body.append(caja);
      } catch (_) {}
    };
    setInterval(revisar, 5 * 60 * 1000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) revisar(); });
    addEventListener('focus', revisar);
    revisar();
  }

  document.addEventListener('DOMContentLoaded', async () => {
    vigilarVersion();
    const caja = document.getElementById('acceso'), form = document.getElementById('acceso-form');
    const campo = document.getElementById('acceso-clave'), error = document.getElementById('acceso-error');
    const boton = document.getElementById('acceso-entrar');
    const guardada = await claveGuardada();
    if (guardada) { clave = guardada; caja.hidden = true; vigilarInactividad(); abrir(); return; }
    campo.focus();
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      error.hidden = true; boton.disabled = true; boton.textContent = 'Comprobando…';
      try {
        const usuario = document.getElementById('acceso-usuario').value;
        const recordar = document.getElementById('acceso-recordar').checked;
        // Solo hay entrada personal: la contrasena abre la ranura de esa persona, que trae la clave de los
        // datos y su nombre. La contrasena maestra (CLAVE_WEB) ya no sirve para entrar.
        if (!usuario.trim()) throw new Error('sin usuario');
        const ranuras = await (await fetchReal('data/usuarios.json', { cache: 'no-store' })).json();
        const r = ranuras[await idRanura(usuario)];
        if (!r) throw new Error('mala');
        const dato = await descifrar(await derivar(campo.value, r.s), aBytes(r.b));
        const k = await crypto.subtle.importKey('raw', aBytes(dato.k), { name: 'AES-GCM' }, true, ['decrypt']);
        if (!(await probar(k))) throw new Error('mala');
        await entrarCon(k, recordar, dato.n);
      } catch (e) {
        error.textContent = e && e.message === 'sin usuario' ? 'Escriba su usuario.' : 'Usuario o contraseña incorrectos. Revíselos e intente de nuevo.'; error.hidden = false;
        campo.select(); boton.disabled = false; boton.textContent = 'Entrar';
      }
    });
  });
})();
