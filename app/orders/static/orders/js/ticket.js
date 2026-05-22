/* =====================================================
   ticket.js
   - Botón "Imprimir" llama a window.print()
   - Si la URL contiene ?auto=1 (viene del POS), abrimos
     automáticamente el diálogo de impresión.
===================================================== */
(function () {
  'use strict';

  const btn = document.querySelector('button.print');
  if (btn) {
    btn.addEventListener('click', () => window.print());
  }

  if (window.location.search.includes('auto=1')) {
    window.addEventListener('load', () => setTimeout(() => window.print(), 200));
  }
})();
