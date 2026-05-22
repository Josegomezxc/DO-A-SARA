/* =====================================================
   order_list.js — filtros en tiempo real para la lista
   de pedidos.
===================================================== */
(function () {
  'use strict';

  const form = document.getElementById('orderFilterForm');
  if (!form) return;

  const qInput = document.getElementById('q-input');
  let timer;
  if (qInput) {
    qInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => form.submit(), 350);
    });
  }
  form.querySelectorAll('.filter-auto').forEach(el => {
    el.addEventListener('change', () => form.submit());
  });
})();
