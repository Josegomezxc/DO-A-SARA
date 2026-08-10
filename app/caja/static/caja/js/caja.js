/* =====================================================
   Caja - formulario dinámico de cobro y factura
   1. Método de pago: efectivo muestra "monto recibido" + vuelto
   2. Tipo de identificación: consumidor final autocompletado;
      RUC / Cédula / Pasaporte muestran los inputs necesarios con
      placeholders orientativos (largo esperado).
   3. Cliente habitual: búsqueda por identificación (única) que
      autocompleta los datos del receptor.
   Vuelto = recibido - total (solo efectivo).
===================================================== */

(function () {
  'use strict';

  var form = document.querySelector('form[data-total]');
  if (!form) return;

  var TOTAL = parseFloat(form.dataset.total) || 0;
  var BUSCAR_URL = form.dataset.buscarUrl || '';

  var metodo = document.getElementById('metodo_pago');
  var recibidoWrap = document.getElementById('recibido-wrap');
  var recibido = document.getElementById('recibido');
  var vueltoBox = document.getElementById('vuelto-box');
  var vueltoAmount = document.getElementById('vuelto-amount');

  var tipo = document.getElementById('tipo_identificacion');
  var tipoWrap = document.getElementById('tipo-wrap');
  var consumidor = document.getElementById('receptor-consumidor');
  var receptorFields = document.getElementById('receptor-fields');
  var identInput = document.getElementById('identificacion');
  var identAyuda = document.getElementById('ident-ayuda');

  // Cliente habitual
  var switchFactura = document.getElementById('switch-factura-datos');
  var buscarCliente = document.getElementById('buscar-cliente');
  var buscarClienteWrap = document.getElementById('buscar-cliente-wrap');
  var clientesResultados = document.getElementById('clientes-resultados');
  var clienteCargado = document.getElementById('cliente-cargado');
  var valoresPorTipo = {};
  var tipoActual = tipo.value;
  var nombresApellidosWrap = document.getElementById('nombres-apellidos-wrap');
  var razonSocialWrap = document.getElementById('razon-social-wrap');
  var camposCliente = {
    nombres: document.getElementById('nombres'),
    apellidos: document.getElementById('apellidos'),
    razon_social: document.getElementById('razon_social'),
    identificacion: document.getElementById('identificacion'),
    direccion: document.getElementById('direccion'),
    email: document.getElementById('email'),
    telefono: document.getElementById('telefono'),
  };

  var HELP = {
    '04': '13 dígitos (obligatorio). Ej: 1790012345001',
    '05': '10 dígitos (obligatorio). Ej: 1712345678',
    '06': 'Entre 5 y 20 caracteres (obligatorio). Ej: A1234567',
  };
  var IDENT_PLACEHOLDER = {
    '04': 'RUC del cliente',
    '05': 'Cédula del cliente',
    '06': 'Número de pasaporte',
  };

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatMoney(n) {
    var v = Number(n) || 0;
    return '$' + v.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function actualizarPago() {
    var esEfectivo = metodo.value === 'efectivo';
    recibidoWrap.classList.toggle('d-none', !esEfectivo);
    if (!esEfectivo) {
      vueltoBox.classList.add('d-none');
      return;
    }
    var rec = parseFloat(String(recibido.value).replace(',', '.'));
    if (Number.isFinite(rec) && rec >= TOTAL) {
      vueltoBox.classList.remove('d-none');
      vueltoAmount.textContent = formatMoney(rec - TOTAL);
    } else {
      vueltoBox.classList.add('d-none');
    }
  }

  function actualizarReceptor() {
    var esConsumidor = !switchFactura.checked;
    if (esConsumidor) tipo.value = '07';
    consumidor.classList.toggle('d-none', !esConsumidor);
    receptorFields.classList.toggle('d-none', esConsumidor);
    tipoWrap.classList.toggle('d-none', esConsumidor);
    buscarClienteWrap.classList.toggle('d-none', esConsumidor);
    identInput.placeholder = esConsumidor ? '' : IDENT_PLACEHOLDER[tipo.value] || '';
    identAyuda.textContent = esConsumidor ? '' : HELP[tipo.value] || '';
    // RUC: solo razón social; cédula/pasaporte: nombres + apellidos
    var esRuc = tipo.value === '04';
    nombresApellidosWrap.classList.toggle('d-none', esConsumidor || esRuc);
    razonSocialWrap.classList.toggle('d-none', esConsumidor || !esRuc);
  }

  // ---------- Cliente habitual (búsqueda por identificación) ----------

  var clientesCache = [];
  var debounceTimer = null;

  function ocultarResultados() {
    clientesResultados.hidden = true;
  }

  function mostrarResultados(lista) {
    clientesResultados.innerHTML = '';
    if (!lista.length) {
      var vacio = document.createElement('li');
      vacio.className = 'caja-clientes-empty';
      vacio.textContent = 'No se encontró ningún cliente con ese número.';
      clientesResultados.appendChild(vacio);
    } else {
      lista.forEach(function (c, i) {
        var li = document.createElement('li');
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'caja-cliente-item';
        btn.dataset.index = String(i);
        btn.innerHTML =
          '<strong>' + escapeHtml(c.nombre) + '</strong>' +
          '<span>' + escapeHtml(c.identificacion) + '</span>';
        li.appendChild(btn);
        clientesResultados.appendChild(li);
      });
    }
    clientesResultados.hidden = false;
  }

  function buscar() {
    var q = buscarCliente.value.trim();
    if (q.length < 2) {
      ocultarResultados();
      return;
    }
    if (!BUSCAR_URL) return;
    fetch(BUSCAR_URL + '?q=' + encodeURIComponent(q))
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (q !== buscarCliente.value.trim()) return;
        clientesCache = data.clientes || [];
        mostrarResultados(clientesCache);
      })
      .catch(function () {
        ocultarResultados();
      });
  }

  function seleccionarCliente(c) {
    tipo.value = c.tipo_identificacion;
    if (c.tipo_identificacion === '04') {
      camposCliente.razon_social.value = c.nombre || '';
      camposCliente.nombres.value = '';
      camposCliente.apellidos.value = '';
    } else {
      if (c.nombres && c.apellidos) {
        camposCliente.nombres.value = c.nombres;
        camposCliente.apellidos.value = c.apellidos;
      } else {
        // Clientes guardados antes de los campos separados: la última
        // palabra va a Apellidos y el resto a Nombres (la cajera corrige).
        var partes = (c.nombre || '').trim().split(/\s+/);
        if (partes.length > 1) {
          camposCliente.apellidos.value = partes.pop();
          camposCliente.nombres.value = partes.join(' ');
        } else {
          camposCliente.nombres.value = partes[0] || '';
          camposCliente.apellidos.value = '';
        }
      }
      camposCliente.razon_social.value = '';
    }
    camposCliente.identificacion.value = c.identificacion;
    camposCliente.direccion.value = c.direccion || '';
    camposCliente.email.value = c.email || '';
    camposCliente.telefono.value = c.telefono || '';
    valoresPorTipo[c.tipo_identificacion] = c.identificacion;
    tipoActual = c.tipo_identificacion;
    actualizarReceptor();
    buscarCliente.value = '';
    ocultarResultados();
    clienteCargado.classList.remove('d-none');
    // El .value programático no dispara input: revalidar los campos
    // rellenados para borrar estados viejos (ej. "obligatorio" en vacío).
    document.querySelectorAll('#receptor-fields [data-validar]').forEach(function (el) {
      el.dispatchEvent(new Event('blur'));
    });
  }

  function limpiarSeleccion() {
    clienteCargado.classList.add('d-none');
  }

  if (buscarCliente) {
    buscarCliente.addEventListener('input', function () {
      clearTimeout(debounceTimer);
      limpiarSeleccion();
      debounceTimer = setTimeout(buscar, 250);
    });
    buscarCliente.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') ocultarResultados();
    });
    clientesResultados.addEventListener('click', function (e) {
      var btn = e.target.closest('.caja-cliente-item');
      if (!btn) return;
      seleccionarCliente(clientesCache[parseInt(btn.dataset.index, 10)]);
    });
    document.addEventListener('click', function (e) {
      if (!e.target.closest('#buscar-cliente') &&
          !e.target.closest('#clientes-resultados')) {
        ocultarResultados();
      }
    });
  }

  metodo.addEventListener('change', actualizarPago);
  recibido.addEventListener('input', actualizarPago);
  identInput.addEventListener('input', function () {
    if (identInput.value.trim()) valoresPorTipo[tipoActual] = identInput.value.trim();
  });
  tipo.addEventListener('change', function () {
    // Guardar el número bajo el tipo anterior antes de cambiarlo.
    if (identInput.value.trim()) valoresPorTipo[tipoActual] = identInput.value.trim();
    // Si se elige Consumidor Final desde el select, el switch se apaga.
    if (tipo.value === '07' && switchFactura) switchFactura.checked = false;
    // Un número cargado (ej. cédula) no vale para otro tipo (RUC/pasaporte):
    // se vacía el campo, pero se restaura al volver al tipo original.
    identInput.value = valoresPorTipo[tipo.value] || '';
    limpiarSeleccion();
    actualizarReceptor();
    tipoActual = tipo.value;
  });

  if (switchFactura) {
    switchFactura.addEventListener('change', function () {
      if (switchFactura.checked) {
        if (tipo.value === '07') {
          tipo.value = '05';
          identInput.value = valoresPorTipo['05'] || identInput.value;
        }
      } else {
        tipo.value = '07';
      }
      actualizarReceptor();
      // Marca el campo como tocado para que validacion.js muestre el
      // estado (requerido vacío, número inválido, etc.) al instante.
      identInput.dispatchEvent(new Event('blur'));
    });
  }

  actualizarPago();
  actualizarReceptor();
})();
