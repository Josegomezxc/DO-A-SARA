/* =====================================================
   POS (Punto de venta) - selects en cascada + tabla
   Flujo:
     1. Elegir categoría
     2. Elegir producto (filtra por categoría)
     3. Botón "Agregar al pedido"
   Tabla con cantidad editable (>=1, sin negativos ni cero)
   Flujo de cobro en 2 pasos:
     a) "Guardar pedido"     -> crea el pedido en la BD, bloquea la tabla
     b) "Imprimir factura"   -> abre el ticket con auto-print
        + "Nuevo pedido"     -> limpia todo para empezar de cero
===================================================== */

(function () {
  'use strict';

  // ---------- Configuración (leída desde data-* en el HTML) ----------
  const $config = document.getElementById('pos-config');
  const POS_CSRF = $config ? $config.dataset.csrf : '';
  const POS_CREATE_URL = $config ? $config.dataset.createUrl : '';

  // ---------- Datos ----------
  let PRODUCTS = [];
  try {
    PRODUCTS = JSON.parse(document.getElementById('pos-productos-data').textContent || '[]');
  } catch (e) {
    PRODUCTS = [];
  }

  const productById = new Map();
  PRODUCTS.forEach(p => productById.set(String(p.id), {
    id: String(p.id),
    nombre: p.nombre,
    precio: parseFloat(p.precio) || 0,
    categoria_id: String(p.categoria_id),
    descripcion: p.descripcion || '',
  }));

  // Carrito en memoria
  const cart = new Map();
  const MAX_QTY = 999;

  // Estado del flujo de cobro:
  //   'editando'  -> el carrito es editable, botón "Guardar pedido"
  //   'guardado'  -> el pedido ya fue creado, botón "Imprimir factura"
  let state = 'editando';
  let savedTicketUrl = null;
  let savedNumero = null;

  // ---------- DOM ----------
  const $cat = document.getElementById('pos-categoria');
  const $prod = document.getElementById('pos-producto');
  const $prodWrap = document.getElementById('pos-producto-wrap');
  const $addWrap = document.getElementById('pos-agregar-wrap');
  const $btnAdd = document.getElementById('pos-btn-agregar');
  const $precioPrev = document.getElementById('pos-precio-preview');

  const $preview = document.getElementById('pos-preview');
  const $previewNombre = document.getElementById('pos-preview-nombre');
  const $previewPrecio = document.getElementById('pos-preview-precio');
  const $previewDesc = document.getElementById('pos-preview-desc');

  const $tbody = document.getElementById('pos-cart-tbody');
  const $empty = document.getElementById('pos-cart-empty');
  const $count = document.getElementById('pos-cart-count');
  const $btnClear = document.getElementById('pos-btn-vaciar');

  const $total = document.getElementById('pos-total');
  const $btnGuardar = document.getElementById('pos-btn-guardar');
  const $btnImprimir = document.getElementById('pos-btn-imprimir');
  const $btnNuevo = document.getElementById('pos-btn-nuevo');
  const $helpText = document.getElementById('pos-help-text');
  const $steps = document.querySelectorAll('#pos-steps .pos-step');

  // ---------- Utils ----------
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function formatMoney(n) {
    const v = Number(n) || 0;
    return '$' + v.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }
  function sanitizeQty(value) {
    let v = parseInt(value, 10);
    if (!Number.isFinite(v) || v < 1) v = 1;
    if (v > MAX_QTY) v = MAX_QTY;
    return v;
  }

  // ---------- Cascada categoría -> producto ----------
  function show(el)  { if (el) el.classList.remove('d-none'); }
  function hide(el)  { if (el) el.classList.add('d-none'); }

  function ocultarPreview() { hide($preview); }

  // Actualiza el indicador de paso activo (1=categoría, 2=producto, 3=confirmar)
  function setActiveStep(n) {
    if (!$steps || !$steps.length) return;
    $steps.forEach(step => {
      const sn = parseInt(step.dataset.step, 10);
      step.classList.remove('active', 'done');
      if (sn < n) step.classList.add('done');
      else if (sn === n) step.classList.add('active');
    });
  }

  function rellenarProductos(catId) {
    $prod.innerHTML = '<option value="">-- Seleccioná un producto --</option>';
    ocultarPreview();
    if (!catId) {
      hide($prodWrap);
      hide($addWrap);
      return;
    }
    const list = PRODUCTS
      .filter(p => String(p.categoria_id) === String(catId))
      .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));

    if (list.length === 0) {
      const opt = document.createElement('option');
      opt.disabled = true;
      opt.textContent = 'No hay productos activos en esta categoría';
      $prod.appendChild(opt);
    } else {
      list.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.nombre} — $${parseFloat(p.precio).toLocaleString('es-AR')}`;
        $prod.appendChild(opt);
      });
    }
    show($prodWrap);
    hide($addWrap);
    $precioPrev.textContent = '';
  }

  if ($cat) {
    $cat.addEventListener('change', () => {
      if (state === 'guardado') reiniciar();
      rellenarProductos($cat.value);
      setActiveStep($cat.value ? 2 : 1);
    });
  }

  if ($prod) {
    $prod.addEventListener('change', () => {
      const id = $prod.value;
      if (!id) {
        hide($addWrap);
        $precioPrev.textContent = '';
        ocultarPreview();
        setActiveStep(2);
        return;
      }
      const p = productById.get(id);
      show($addWrap);
      $precioPrev.textContent = p ? `(${formatMoney(p.precio)})` : '';

      if (p && $preview) {
        $previewNombre.textContent = p.nombre;
        $previewPrecio.textContent = formatMoney(p.precio);
        if (p.descripcion) {
          $previewDesc.textContent = p.descripcion;
          show($previewDesc);
        } else {
          $previewDesc.textContent = '';
          hide($previewDesc);
        }
        show($preview);
      }
      setActiveStep(3);
    });
  }

  // ---------- Agregar al carrito ----------
  if ($btnAdd) {
    $btnAdd.addEventListener('click', () => {
      if (state === 'guardado') reiniciar();

      const id = $prod.value;
      if (!id) return;
      const p = productById.get(id);
      if (!p) return;
      if (cart.has(id)) {
        cart.get(id).cantidad = sanitizeQty(cart.get(id).cantidad + 1);
      } else {
        cart.set(id, {
          id: p.id, nombre: p.nombre, precio: p.precio,
          descripcion: p.descripcion, cantidad: 1,
        });
      }
      render();

      $cat.value = '';
      $prod.innerHTML = '<option value="">-- Seleccioná un producto --</option>';
      hide($prodWrap);
      hide($addWrap);
      $precioPrev.textContent = '';
      ocultarPreview();
      setActiveStep(1);
    });
  }

  // ---------- Render del carrito ----------
  function render() {
    if (!$tbody) return;

    $tbody.querySelectorAll('tr.cart-row').forEach(tr => tr.remove());

    const empty = cart.size === 0;
    if ($empty) $empty.style.display = empty ? '' : 'none';

    const guardado = state === 'guardado';
    let total = 0;
    for (const item of cart.values()) {
      total += item.precio * item.cantidad;
      const tr = document.createElement('tr');
      tr.className = 'cart-row';
      const descHtml = item.descripcion
        ? `<small class="text-muted d-block mt-1">${escapeHtml(item.descripcion)}</small>`
        : '';

      // Si está guardado, la cantidad no se edita y desaparece el botón de borrar
      const qtyCell = guardado
        ? `<span class="font-weight-bold">${item.cantidad}</span>`
        : `<input type="number" class="form-control form-control-sm text-center qty-input mx-auto"
                  data-id="${item.id}" min="1" max="${MAX_QTY}" step="1" value="${item.cantidad}"
                  inputmode="numeric" aria-label="Cantidad">`;
      const delCell = guardado
        ? ''
        : `<button type="button" class="btn btn-sm btn-danger" data-act="del" data-id="${item.id}" title="Quitar" aria-label="Quitar">
             <i class="fas fa-times"></i>
           </button>`;

      tr.innerHTML = `
        <td>
          <strong>${escapeHtml(item.nombre)}</strong>
          ${descHtml}
        </td>
        <td class="text-right align-middle">${formatMoney(item.precio)}</td>
        <td class="text-center align-middle">${qtyCell}</td>
        <td class="text-right align-middle font-weight-bold">${formatMoney(item.precio * item.cantidad)}</td>
        <td class="text-center align-middle">${delCell}</td>`;
      $tbody.appendChild(tr);
    }

    const count = Array.from(cart.values()).reduce((s, i) => s + i.cantidad, 0);
    if ($total) $total.textContent = formatMoney(total);
    if ($count) $count.textContent = count;

    actualizarBotones(empty);
  }

  function actualizarBotones(empty) {
    if (state === 'editando') {
      $btnGuardar.classList.remove('d-none');
      $btnImprimir.classList.add('d-none');
      $btnNuevo.classList.add('d-none');
      $btnGuardar.disabled = empty;
      if ($btnClear) $btnClear.disabled = false;
      if ($helpText) {
        $helpText.textContent = empty
          ? 'El botón se activa cuando agregás al menos un producto al pedido.'
          : 'Revisá las cantidades y guardá el pedido para poder imprimir la factura.';
      }
    } else if (state === 'guardado') {
      $btnGuardar.classList.add('d-none');
      $btnImprimir.classList.remove('d-none');
      $btnNuevo.classList.remove('d-none');
      $btnImprimir.disabled = false;
      if ($btnClear) $btnClear.disabled = true;
      if ($helpText) {
        $helpText.textContent = savedNumero
          ? `Pedido ${savedNumero} guardado. Ahora podés imprimir la factura.`
          : 'Pedido guardado. Ahora podés imprimir la factura.';
      }
    }
  }

  // ---------- Acciones en la tabla ----------
  if ($tbody) {
    $tbody.addEventListener('click', (ev) => {
      if (state === 'guardado') return;
      const btn = ev.target.closest('button[data-act="del"]');
      if (!btn) return;
      cart.delete(btn.dataset.id);
      render();
    });

    // Bloquear teclas no enteras (punto, coma, e, +, -)
    $tbody.addEventListener('keydown', (ev) => {
      if (state === 'guardado') return;
      const t = ev.target;
      if (!t.classList.contains('qty-input')) return;
      if (['.', ',', 'e', 'E', '+', '-'].includes(ev.key)) {
        ev.preventDefault();
      }
    });

    $tbody.addEventListener('input', (ev) => {
      if (state === 'guardado') return;
      const t = ev.target;
      if (!t.classList.contains('qty-input')) return;
      // Forzar solo enteros: quitar cualquier caracter no numérico
      t.value = t.value.replace(/[^0-9]/g, '');
      const item = cart.get(t.dataset.id);
      if (!item) return;
      const v = parseInt(t.value, 10);
      if (Number.isFinite(v) && v >= 1 && v <= MAX_QTY) {
        item.cantidad = v;
        render();
      }
    });

    // Al perder foco, corregir valores fuera de rango
    $tbody.addEventListener('blur', (ev) => {
      if (state === 'guardado') return;
      const t = ev.target;
      if (!t.classList.contains('qty-input')) return;
      const item = cart.get(t.dataset.id);
      if (!item) return;
      item.cantidad = sanitizeQty(t.value);
      render();
    }, true);

    // Bloquear pegado de valores no enteros
    $tbody.addEventListener('paste', (ev) => {
      const t = ev.target;
      if (!t.classList.contains('qty-input')) return;
      const paste = (ev.clipboardData || window.clipboardData).getData('text');
      if (!/^\d+$/.test(paste)) {
        ev.preventDefault();
      }
    });
  }

  if ($btnClear) {
    $btnClear.addEventListener('click', () => {
      if (state === 'guardado') return;
      if (cart.size === 0) return;
      if (confirm('¿Vaciar el pedido?')) {
        cart.clear();
        render();
      }
    });
  }

  // ---------- Guardar pedido ----------
  async function guardarPedido() {
    if (cart.size === 0 || state !== 'editando') return;

    for (const item of cart.values()) {
      item.cantidad = sanitizeQty(item.cantidad);
    }

    const payload = {
      items: Array.from(cart.values()).map(i => ({
        producto_id: i.id, cantidad: i.cantidad,
      })),
      completar: true,
    };

    $btnGuardar.disabled = true;
    const originalLabel = $btnGuardar.innerHTML;
    $btnGuardar.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Guardando...';

    try {
      const resp = await fetch(POS_CREATE_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': POS_CSRF,
        },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data.error || 'Error al guardar.');

      savedTicketUrl = data.ticket_url;
      savedNumero = data.numero;
      state = 'guardado';
      render();
      flash(`Pedido ${data.numero} guardado por ${formatMoney(data.total)}`);
    } catch (err) {
      alert('Error al guardar el pedido: ' + err.message);
      $btnGuardar.innerHTML = originalLabel;
      $btnGuardar.disabled = cart.size === 0;
    }
  }

  function imprimirFactura() {
    if (state !== 'guardado' || !savedTicketUrl) return;
    window.open(savedTicketUrl, '_blank');
  }

  function reiniciar() {
    cart.clear();
    state = 'editando';
    savedTicketUrl = null;
    savedNumero = null;
    // Restaurar texto original del botón guardar (por si quedó "Guardando...")
    $btnGuardar.innerHTML = '<i class="fas fa-save"></i> Guardar pedido';
    render();
  }

  if ($btnGuardar) $btnGuardar.addEventListener('click', guardarPedido);
  if ($btnImprimir) $btnImprimir.addEventListener('click', imprimirFactura);
  if ($btnNuevo) $btnNuevo.addEventListener('click', reiniciar);

  function flash(msg) {
    const toast = document.createElement('div');
    toast.className = 'pos-toast';
    toast.setAttribute('role', 'status');
    toast.innerHTML = `<i class="fas fa-check-circle"></i><span>${escapeHtml(msg)}</span>`;
    document.body.appendChild(toast);
    // Trigger animation entrada
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  render();
})();
