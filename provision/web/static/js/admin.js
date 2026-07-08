// F3.1/F3.2 — Consola admin (JS estático, CSP sin inline).
// Render SIEMPRE con createElement/textContent: los datos vienen de BD
// (creados por admins) y no deben interpretarse como HTML (anti-XSS).
// Toda mutación envía X-Requested-With (los endpoints F2 lo exigen).
'use strict';

const XRW = { 'X-Requested-With': 'XMLHttpRequest' };
const JSON_HDRS = { 'Content-Type': 'application/json', ...XRW };

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

function btn(text, className, onClick) {
  const b = el('button', { className: className || 'btn-secondary', text });
  b.addEventListener('click', onClick);
  return b;
}

async function api(method, url, body) {
  const opts = { method, headers: method === 'GET' ? {} : (body !== undefined ? JSON_HDRS : XRW) };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const resp = await fetch(url, opts);
  let data = null;
  try { data = await resp.json(); } catch (e) { /* respuesta sin cuerpo */ }
  if (!resp.ok) {
    const detail = data && data.detail ? data.detail : resp.status;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}

function notify(msg, isError) {
  const box = document.getElementById('admin-msg');
  box.textContent = msg;
  box.className = isError ? 'msg msg-error' : 'msg';
  if (msg) setTimeout(() => { if (box.textContent === msg) box.textContent = ''; }, 6000);
}

function table(headers, rows) {
  const thead = el('tr', {}, headers.map((h) => el('th', { text: h })));
  const t = el('table', {}, [thead]);
  rows.forEach((r) => t.appendChild(r));
  return t;
}

function content() { return document.getElementById('admin-content'); }

// --- Instancias -------------------------------------------------------------
async function loadInstances(cursor, append) {
  const url = '/admin/instances?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : '');
  let data;
  try { data = await api('GET', url); } catch (e) { notify('Error: ' + e.message, true); return; }
  const rows = (data.instances || []).map((i) => {
    const destroy = btn('Destruir', 'btn-danger', async () => {
      if (!confirm('¿Destruir ' + i.nombre + ' (' + i.tipo + ')? Esta acción es irreversible.')) return;
      try {
        await api('POST', '/admin/instances/' + encodeURIComponent(i.nombre) + '/destroy?tipo=' + encodeURIComponent(i.tipo));
        notify('Destruida ' + i.nombre);
        loadSection('instances');
      } catch (e) { notify('Error: ' + e.message, true); }
    });
    return el('tr', {}, [
      el('td', { text: i.tipo }), el('td', { text: i.nombre }),
      el('td', { text: i.alumno || '-' }), el('td', { text: i.lab }),
      el('td', { text: i.estado }), el('td', { text: i.ip || '-' }),
      el('td', { text: i.last_seen || '-' }), el('td', {}, [destroy])
    ]);
  });
  const root = content();
  if (!append) {
    root.textContent = '';
    root.appendChild(el('h3', { text: 'Instancias (VMs + apps)' }));
    root.appendChild(table(['Tipo', 'Nombre', 'Alumno', 'Lab/App', 'Estado', 'IP', 'Última señal', 'Acciones'], rows));
  } else {
    const t = root.querySelector('table');
    rows.forEach((r) => t.appendChild(r));
    const old = document.getElementById('btn-more-inst');
    if (old) old.remove();
  }
  if (data.has_more && data.next_cursor) {
    const more = btn('Cargar más', 'btn-secondary', () => loadInstances(data.next_cursor, true));
    more.id = 'btn-more-inst';
    root.appendChild(more);
  }
}

// --- Labs -------------------------------------------------------------------
async function loadLabs() {
  let data;
  try { data = await api('GET', '/admin/labs'); } catch (e) { notify('Error: ' + e.message, true); return; }
  const rows = (data.labs || []).map((l) => {
    const toggle = btn(l.activo ? 'Desactivar' : 'Activar', 'btn-secondary', async () => {
      try {
        await api('PATCH', '/admin/labs/' + encodeURIComponent(l.nombre), { activo: l.activo ? 0 : 1 });
        loadSection('labs');
      } catch (e) { notify('Error: ' + e.message, true); }
    });
    const edit = btn('Editar', 'btn-secondary', async () => {
      const imagen = prompt('Imagen del lab:', l.imagen);
      if (imagen === null) return;
      const deadline = prompt('Deadline ISO-8601 (vacío = sin deadline):', l.deadline || '');
      if (deadline === null) return;
      try {
        await api('PATCH', '/admin/labs/' + encodeURIComponent(l.nombre), { imagen, deadline });
        notify('Lab ' + l.nombre + ' actualizado');
        loadSection('labs');
      } catch (e) { notify('Error: ' + e.message, true); }
    });
    return el('tr', {}, [
      el('td', { text: l.nombre }), el('td', { text: l.imagen }),
      el('td', { text: l.deadline || '-' }), el('td', { text: l.activo ? 'sí' : 'no' }),
      el('td', { text: String(l.matriculados) }), el('td', { text: String(l.instancias_vivas) }),
      el('td', {}, [toggle, edit])
    ]);
  });

  const inNombre = el('input', { placeholder: 'nombre (minúsculas, sin app-)', required: '' });
  const inImagen = el('input', { placeholder: 'imagen', value: 'local:lab-vm-base' });
  const inDeadline = el('input', { placeholder: 'deadline ISO-8601 (opcional)' });
  const form = el('form', { className: 'inline-form' }, [
    inNombre, inImagen, inDeadline,
    el('button', { type: 'submit', className: 'btn-primary', text: 'Crear lab' })
  ]);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('POST', '/admin/labs', {
        nombre: inNombre.value.trim(),
        imagen: inImagen.value.trim() || 'local:lab-vm-base',
        deadline: inDeadline.value.trim() || null
      });
      notify('Lab creado');
      loadSection('labs');
    } catch (e2) { notify('Error: ' + e2.message, true); }
  });

  const root = content();
  root.textContent = '';
  root.appendChild(el('h3', { text: 'Labs' }));
  root.appendChild(table(['Nombre', 'Imagen', 'Deadline', 'Activo', 'Matriculados', 'Instancias vivas', 'Acciones'], rows));
  root.appendChild(el('h4', { text: 'Alta de lab' }));
  root.appendChild(form);
}

// --- Matrículas ---------------------------------------------------------------
async function loadEnrollments(cursor, append, labFilter) {
  const filter = labFilter !== undefined ? labFilter
    : (document.getElementById('enr-filter') ? document.getElementById('enr-filter').value.trim() : '');
  let url = '/admin/enrollments?limit=50';
  if (filter) url += '&lab=' + encodeURIComponent(filter);
  if (cursor) url += '&cursor=' + encodeURIComponent(cursor);
  let data;
  try { data = await api('GET', url); } catch (e) { notify('Error: ' + e.message, true); return; }

  const rows = (data.enrollments || []).map((m) => {
    const toggle = btn(m.active ? 'Baja' : 'Realta', 'btn-secondary', async () => {
      try {
        await api('PATCH', '/admin/enrollments', { email: m.email, lab: m.lab, active: m.active ? 0 : 1 });
        loadSection('enrollments');
      } catch (e) { notify('Error: ' + e.message, true); }
    });
    const launch = btn('Lanzar VM', 'btn-primary', async () => {
      try {
        const r = await api('POST', '/admin/instances/launch', { alumno: m.alumno_id, lab: m.lab });
        notify('Instancia ' + r.instancia + ': ' + r.estado);
      } catch (e) { notify('Error: ' + e.message, true); }
    });
    const actions = m.active ? [toggle, launch] : [toggle];
    return el('tr', {}, [
      el('td', { text: m.alumno_id }), el('td', { text: m.email }),
      el('td', { text: m.lab }), el('td', { text: m.active ? 'sí' : 'no' }),
      el('td', { text: m.estado_instancia }), el('td', {}, actions)
    ]);
  });

  const root = content();
  if (!append) {
    root.textContent = '';
    root.appendChild(el('h3', { text: 'Matrículas' }));

    const filterInput = el('input', { id: 'enr-filter', placeholder: 'filtrar por lab', value: filter });
    const filterBtn = btn('Filtrar', 'btn-secondary', () => loadEnrollments(null, false));
    root.appendChild(el('div', { className: 'inline-form' }, [filterInput, filterBtn]));

    root.appendChild(table(['Alumno', 'Email', 'Lab', 'Activa', 'Instancia', 'Acciones'], rows));

    const inAlumno = el('input', { placeholder: 'alumno_id', required: '' });
    const inEmail = el('input', { placeholder: 'email', type: 'email', required: '' });
    const inLab = el('input', { placeholder: 'lab', required: '' });
    const form = el('form', { className: 'inline-form' }, [
      inAlumno, inEmail, inLab,
      el('button', { type: 'submit', className: 'btn-primary', text: 'Matricular' })
    ]);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await api('POST', '/admin/enrollments', {
          alumno_id: inAlumno.value.trim(),
          email: inEmail.value.trim(),
          lab: inLab.value.trim()
        });
        notify('Matrícula creada');
        loadSection('enrollments');
      } catch (e2) { notify('Error: ' + e2.message, true); }
    });
    root.appendChild(el('h4', { text: 'Alta de matrícula' }));
    root.appendChild(form);
  } else {
    const t = root.querySelector('table');
    rows.forEach((r) => t.appendChild(r));
    const old = document.getElementById('btn-more-enr');
    if (old) old.remove();
  }
  if (data.has_more && data.next_cursor) {
    const more = btn('Cargar más', 'btn-secondary', () => loadEnrollments(data.next_cursor, true));
    more.id = 'btn-more-enr';
    root.appendChild(more);
  }
}

// --- Apps stateless -----------------------------------------------------------
function appEditForm(a, container) {
  const inNombre = el('input', { value: a.nombre, placeholder: 'nombre' });
  const inImagen = el('input', { value: a.imagen, placeholder: 'imagen local:app-*' });
  const inPuerto = el('input', { value: String(a.puerto_http), type: 'number', min: '3000', max: '9999' });
  const inCpu = el('input', { value: String(a.cpu), type: 'number', min: '1' });
  const inMem = el('input', { value: String(a.memory_mb), type: 'number', min: '256' });
  const inShared = el('input', { type: 'checkbox' }); inShared.checked = !!a.shared;
  const inAlways = el('input', { type: 'checkbox' }); inAlways.checked = !!a.always_on;
  const inDesc = el('input', { value: a.descripcion || '', placeholder: 'descripción' });
  const inLabs = el('input', { placeholder: 'labs separados por coma (vacío = no tocar)' });
  const form = el('form', { className: 'inline-form' }, [
    el('label', { text: 'nombre ' }, [inNombre]),
    el('label', { text: 'imagen ' }, [inImagen]),
    el('label', { text: 'puerto ' }, [inPuerto]),
    el('label', { text: 'cpu ' }, [inCpu]),
    el('label', { text: 'mem MB ' }, [inMem]),
    el('label', { text: 'shared ' }, [inShared]),
    el('label', { text: 'always_on ' }, [inAlways]),
    el('label', { text: 'desc ' }, [inDesc]),
    el('label', { text: 'labs ' }, [inLabs]),
    el('button', { type: 'submit', className: 'btn-primary', text: 'Guardar' })
  ]);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {
      nombre: inNombre.value.trim(),
      imagen: inImagen.value.trim(),
      puerto_http: parseInt(inPuerto.value, 10),
      cpu: parseInt(inCpu.value, 10),
      memory_mb: parseInt(inMem.value, 10),
      shared: inShared.checked ? 1 : 0,
      always_on: inAlways.checked ? 1 : 0,
      descripcion: inDesc.value
    };
    const labsRaw = inLabs.value.trim();
    if (labsRaw) body.labs = labsRaw.split(',').map((s) => s.trim()).filter(Boolean);
    try {
      await api('PATCH', '/admin/apps/' + encodeURIComponent(a.id), body);
      notify('App ' + a.id + ' actualizada');
      loadSection('apps');
    } catch (e2) { notify('Error: ' + e2.message, true); }
  });
  container.textContent = '';
  container.appendChild(form);
}

async function loadApps() {
  let data;
  try { data = await api('GET', '/admin/apps'); } catch (e) { notify('Error: ' + e.message, true); return; }
  const root = content();
  root.textContent = '';
  root.appendChild(el('h3', { text: 'Apps stateless' }));

  const editZone = el('div', { id: 'app-edit-zone' });
  const rows = (data.apps || []).map((a) => {
    const actions = [];
    actions.push(btn('Editar', 'btn-secondary', () => appEditForm(a, editZone)));
    if (a.activo) {
      actions.push(btn('Desactivar', 'btn-danger', async () => {
        if (!confirm('Desactivar ' + a.id + ' destruirá sus instancias vivas (encolado). ¿Continuar?')) return;
        try {
          const r = await api('DELETE', '/admin/apps/' + encodeURIComponent(a.id));
          notify('App desactivada; instancias encoladas: ' + r.instancias_encoladas);
          loadSection('apps');
        } catch (e) { notify('Error: ' + e.message, true); }
      }));
      if (a.shared) {
        actions.push(btn('Start', 'btn-secondary', async () => {
          try {
            const r = await api('POST', '/admin/apps/' + encodeURIComponent(a.id) + '/start');
            notify('Start ' + a.id + ': ' + (r.estado || 'ok'));
          } catch (e) { notify('Error: ' + e.message, true); }
        }));
        actions.push(btn('Stop', 'btn-secondary', async () => {
          try {
            await api('POST', '/admin/apps/' + encodeURIComponent(a.id) + '/stop');
            notify('Stop ' + a.id + ' ok');
          } catch (e) { notify('Error: ' + e.message, true); }
        }));
        actions.push(btn('Reset', 'btn-secondary', async () => {
          if (!confirm('Reset (stop + start) de la instancia shared de ' + a.id + '?')) return;
          try {
            await api('POST', '/admin/apps/' + encodeURIComponent(a.id) + '/stop');
            const r = await api('POST', '/admin/apps/' + encodeURIComponent(a.id) + '/start');
            notify('Reset ' + a.id + ': ' + (r.estado || 'ok'));
          } catch (e) { notify('Error: ' + e.message, true); }
        }));
      }
    } else {
      actions.push(btn('Reactivar', 'btn-secondary', async () => {
        try {
          await api('PATCH', '/admin/apps/' + encodeURIComponent(a.id), { activo: 1 });
          notify('App ' + a.id + ' reactivada');
          loadSection('apps');
        } catch (e) { notify('Error: ' + e.message, true); }
      }));
    }
    return el('tr', {}, [
      el('td', { text: a.id }), el('td', { text: a.nombre }),
      el('td', { text: a.imagen }), el('td', { text: String(a.puerto_http) }),
      el('td', { text: a.shared ? 'sí' : 'no' }), el('td', { text: a.always_on ? 'sí' : 'no' }),
      el('td', { text: a.cpu + ' / ' + a.memory_mb + 'MB' }),
      el('td', { text: a.activo ? 'sí' : 'no' }),
      el('td', {}, actions)
    ]);
  });
  root.appendChild(table(['ID', 'Nombre', 'Imagen', 'Puerto', 'Shared', 'AlwaysOn', 'CPU/Mem', 'Activa', 'Acciones'], rows));
  root.appendChild(editZone);

  // Alta de app
  const inId = el('input', { placeholder: 'id (slug)', required: '' });
  const inNombre = el('input', { placeholder: 'nombre visible', required: '' });
  const inImagen = el('input', { placeholder: 'imagen local:app-*', required: '' });
  const inPuerto = el('input', { placeholder: 'puerto', type: 'number', min: '3000', max: '9999', required: '' });
  const inCpu = el('input', { placeholder: 'cpu', type: 'number', value: '2', min: '1' });
  const inMem = el('input', { placeholder: 'mem MB', type: 'number', value: '2048', min: '256' });
  const inShared = el('input', { type: 'checkbox' }); inShared.checked = true;
  const inAlways = el('input', { type: 'checkbox' });
  const inLabs = el('input', { placeholder: 'labs separados por coma' });
  const inDesc = el('input', { placeholder: 'descripción' });
  const form = el('form', { className: 'inline-form' }, [
    inId, inNombre, inImagen, inPuerto, inCpu, inMem,
    el('label', { text: 'shared ' }, [inShared]),
    el('label', { text: 'always_on ' }, [inAlways]),
    inLabs, inDesc,
    el('button', { type: 'submit', className: 'btn-primary', text: 'Crear app' })
  ]);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('POST', '/admin/apps', {
        id: inId.value.trim(),
        nombre: inNombre.value.trim(),
        imagen: inImagen.value.trim(),
        puerto_http: parseInt(inPuerto.value, 10),
        cpu: parseInt(inCpu.value, 10) || 2,
        memory_mb: parseInt(inMem.value, 10) || 2048,
        shared: inShared.checked ? 1 : 0,
        always_on: inAlways.checked ? 1 : 0,
        descripcion: inDesc.value || null,
        labs: inLabs.value.split(',').map((s) => s.trim()).filter(Boolean)
      });
      notify('App creada');
      loadSection('apps');
    } catch (e2) { notify('Error: ' + e2.message, true); }
  });
  root.appendChild(el('h4', { text: 'Alta de app' }));
  root.appendChild(form);
}

// --- Router de secciones -------------------------------------------------------
function loadSection(section) {
  if (section === 'instances') loadInstances();
  else if (section === 'labs') loadLabs();
  else if (section === 'enrollments') loadEnrollments();
  else if (section === 'apps') loadApps();
}

document.querySelectorAll('.btn-tab').forEach((b) => {
  b.addEventListener('click', () => loadSection(b.dataset.section));
});

document.getElementById('btn-logout').addEventListener('click', async () => {
  await fetch('/admin/logout', { method: 'POST', headers: XRW });
  window.location.href = '/admin/login';
});

loadSection('instances');
