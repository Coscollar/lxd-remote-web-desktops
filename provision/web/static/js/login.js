// F3.1 — Login alumno/admin (JS estático: la CSP prohíbe scripts inline).
// El modo admin llega por atributo DOM (data-admin), no por Jinja en JS.
'use strict';

document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  const isAdmin = form.dataset.admin === 'true';
  const endpoint = isAdmin ? '/admin/auth/request' : '/auth/request';
  const email = document.getElementById('email').value;
  const msg = document.getElementById('msg');
  msg.textContent = 'Enviando...';
  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({ email })
    });
    if (resp.ok) {
      msg.textContent = 'Revisa tu correo. Si no lo ves, comprueba spam.';
    } else if (resp.status === 429) {
      msg.textContent = 'Demasiadas peticiones. Espera unos minutos.';
    } else {
      msg.textContent = 'Error. Inténtalo de nuevo.';
    }
  } catch (err) {
    msg.textContent = 'Error de red.';
  }
});
