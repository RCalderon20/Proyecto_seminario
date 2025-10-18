// Mejora rápida del buscador del catálogo
document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('.catalog-search');
  if (!form) return;
  const input = form.querySelector('input[name="q"]');

  // Enter para enviar con trim
  form.addEventListener('submit', (e) => {
    if (input) input.value = (input.value || '').trim();
  });

  // Atajo: ESC limpia y envía (muestra todo)
  input?.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      input.value = '';
      form.submit();
    }
  });
});

// Bootstrap client-side validation
document.addEventListener('DOMContentLoaded', () => {
  const forms = document.querySelectorAll('form[novalidate]');
  forms.forEach(form => {
    form.addEventListener('submit', e => {
      if (!form.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
      }
      form.classList.add('was-validated');
    }, false);
  });
});


// Toggle password visibility on login
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('btnTogglePwd');
  const input = document.getElementById('loginPassword');
  const eyeText = document.getElementById('eyeText');
  if (btn && input && eyeText) {
    btn.addEventListener('click', () => {
      const isPwd = input.getAttribute('type') === 'password';
      input.setAttribute('type', isPwd ? 'text' : 'password');
      eyeText.textContent = isPwd ? 'Ocultar' : 'Mostrar';
      input.focus();
    });
  }
});
