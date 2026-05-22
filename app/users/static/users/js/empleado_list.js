/* =====================================================
   empleado_list.js — filtros en tiempo real para la
   lista de empleados.
===================================================== */
(function () {
  'use strict';

  const form = document.getElementById('empleadoFilterForm');
  if (!form) return;

  const qInput = document.getElementById('q-input');
  let timer;
  if (qInput) {
    qInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => form.submit(), 350);
    });
  }
  form.querySelectorAll('select.filter-auto').forEach(sel => {
    sel.addEventListener('change', () => form.submit());
  });
})();
