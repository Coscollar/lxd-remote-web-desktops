// F3.1 — Dashboard alumno (JS estático, CSP sin inline).
// Render con createElement/textContent (NUNCA innerHTML interpolado: los
// datos vienen de BD y podrían contener HTML). API de apps vía /api/apps/*
// (F3.0: /apps/* en Nginx proxya al contenedor, no a la API).
'use strict';

function el(tag, props, children) {
  const node = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      // Guard anti-regresión: nunca fijar handlers inline vía props.
      if (k.toLowerCase().startsWith('on')) throw new Error('atributo prohibido: ' + k);
      if (k === 'className') node.className = v;
      else if (k === 'text') node.textContent = v;
      else node.setAttribute(k, v);
    }
  }
  (children || []).forEach((c) => node.appendChild(c));
  return node;
}

const XRW = { 'X-Requested-With': 'XMLHttpRequest' };

async function selectLab(lab) {
  const resp = await fetch('/lab/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...XRW },
    body: JSON.stringify({ lab })
  });
  if (resp.ok) {
    const data = await resp.json();
    // Defensa en profundidad: solo rutas relativas del propio origen.
    if (typeof data.redirect === 'string' && data.redirect.startsWith('/')
        && !data.redirect.startsWith('//')) {
      window.location.href = data.redirect;
    }
  } else {
    alert('No se pudo seleccionar el lab');
  }
}

function showApp(appId) {
  const url = '/apps/' + encodeURIComponent(appId) + '/';
  const iframe = el('iframe', { src: url, sandbox: 'allow-scripts allow-forms' });
  iframe.style.cssText = 'width:100%;height:100%;border:0';
  const closeBtn = el('button', { className: 'btn-close', text: 'X' });
  const frame = el('div', { className: 'app-frame' }, [closeBtn, iframe]);
  const overlay = el('div', { className: 'app-overlay' }, [frame]);
  closeBtn.addEventListener('click', () => overlay.remove());
  document.body.appendChild(overlay);
}

async function pollApp(appId) {
  for (let i = 0; i < 30; i++) {
    const status = await fetch('/api/apps/' + encodeURIComponent(appId) + '/status')
      .then((r) => r.json())
      .catch(() => ({ estado: 'error-red' }));
    if (status.estado === 'lista') { showApp(appId); return; }
    if (status.estado === 'error') { alert('Error al lanzar la app'); return; }
    await new Promise((r) => setTimeout(r, 2000));
  }
  alert('La app tardó demasiado en arrancar');
}

async function openApp(appId) {
  const resp = await fetch('/api/apps/' + encodeURIComponent(appId) + '/start', {
    method: 'POST',
    headers: XRW
  });
  if (resp.status === 202) {
    pollApp(appId);
  } else if (resp.ok) {
    showApp(appId);
  } else {
    alert('No se pudo lanzar la app');
  }
}

function labCard(lab, current) {
  const active = lab.lab === current;
  const btn = el('button', { className: 'btn-primary', text: 'Abrir escritorio' });
  btn.addEventListener('click', () => selectLab(lab.lab));
  return el('div', { className: 'card' + (active ? ' active' : '') }, [
    el('h3', { text: lab.lab }),
    el('p', { text: 'Estado: ' + (lab.estado_instancia || 'inexistente') }),
    btn
  ]);
}

function appCard(app) {
  const btn = el('button', { className: 'btn-primary', text: 'Abrir app' });
  btn.addEventListener('click', () => openApp(app.id));
  return el('div', { className: 'card' }, [
    el('h3', { text: app.nombre }),
    el('p', { text: app.descripcion || '' }),
    el('p', {}, [el('small', { text: app.shared ? 'compartida' : 'por alumno' })]),
    btn
  ]);
}

async function loadDashboard() {
  const [labsResp, appsResp] = await Promise.all([
    fetch('/api/my-labs').then((r) => r.json()).catch(() => ({ labs: [] })),
    fetch('/api/apps').then((r) => r.json()).catch(() => ({ apps: [] }))
  ]);
  const root = document.getElementById('dashboard-content');
  root.textContent = '';
  root.appendChild(el('h2', { text: 'Tus laboratorios' }));
  const labCards = el('div', { className: 'cards' });
  (labsResp.labs || []).forEach((lab) => labCards.appendChild(labCard(lab, labsResp.current)));
  root.appendChild(labCards);
  if ((appsResp.apps || []).length > 0) {
    root.appendChild(el('h2', { text: 'Apps stateless' }));
    const appCards = el('div', { className: 'cards' });
    appsResp.apps.forEach((app) => appCards.appendChild(appCard(app)));
    root.appendChild(appCards);
  }
}

document.getElementById('btn-logout').addEventListener('click', async () => {
  await fetch('/logout', { method: 'POST', headers: XRW });
  window.location.href = '/';
});

loadDashboard();
