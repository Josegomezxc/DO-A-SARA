/* =====================================================
   Validación en tiempo real (Bootstrap 4, JS puro)
   Se activa sola: escanea `form [data-validar]`.

   Validadores (separados por espacio):
     requerido   -> no vacío
     email       -> formato email (opcional si está vacío)
     numero      -> número >= 0 (con tope de dígitos enteros y decimales)
     total       -> número >= data-validar-total (monto recibido)
     maxval      -> número <= data-validar-max-val (descuento)
     password    -> mín. data-validar-min (8) y no solo números
     usuario     -> 3-150, solo [\w.@+-]
     cedula      -> cédula ecuatoriana (módulo 10)
     ruc         -> RUC ecuatoriano (módulo 11)
     pasaporte   -> 5-20 caracteres alfanuméricos
     identificacion -> según el select indicado en data-validar-tipo
     imagen      -> extensión y tamaño (File API, antes de subir)

   Otros atributos:
     data-validar-tipo="#id_select"  -> revalida al cambiar el select
     data-validar-disponible="/url/" -> chequeo async de disponibilidad
     data-validar-min="8" / data-validar-total="19.50"
     data-validar-max-val="8.45" / data-validar-imagen-max="5"
     data-validar-imagen-ext="jpg,jpeg,png,webp,gif"
     data-validar-max-int="8" (máx. dígitos enteros, default 8)
     data-validar-max-dec="2" (máx. decimales, default 2)

   UX: al blur muestra el estado; luego valida en vivo con cada tecla.
   Éxito -> .is-valid + "✓ Correcto" | Error -> .is-invalid + mensaje.
   Al enviar: bloquea el submit si hay errores y enfoca el primero.
===================================================== */

(function () {
  'use strict';

  var MENSAJES = {
    requerido: 'Este campo es obligatorio.',
    email: 'Ingresá un email válido.',
    usuario: 'Solo letras, números y @ . + - _ (de 3 a 150 caracteres).',
    password: 'Debe tener al menos 8 caracteres y no ser solo números.',
    numero: 'Ingresá un número válido (mayor o igual a 0).',
    total: 'El monto recibido no cubre el total.',
    maxval: 'El valor supera el máximo permitido.',
    cedula: 'La cédula no es válida (dígito verificador incorrecto).',
    ruc: 'El RUC no es válido (dígito verificador incorrecto).',
    pasaporte: 'El pasaporte solo puede contener letras y números.',
    identificacion: 'La identificación no es válida.',
    imagen_ext: 'Formato de imagen no permitido. Usá: jpg, jpeg, png, webp, gif.',
    imagen_size: 'La imagen supera el máximo de 5 MB.',
  };

  var IMAGEN_EXT_DEFAULT = 'jpg,jpeg,png,webp,gif';
  var IMAGEN_MAX_DEFAULT = 5;
  var NUM_MAX_INT_DEFAULT = 8;
  var NUM_MAX_DEC_DEFAULT = 2;
  var DISPONIBLE_OK = 'Usuario disponible';
  var DISPONIBLE_ERROR = 'Ese nombre de usuario ya está en uso.';

  // ---------- Estructura de números (compartida por numero/total/maxval) ----------
  function estructuraNumero(el, valor) {
    var raw = String(valor || '').trim();
    var m = /^(\d+)(?:[.,](\d+))?$/.exec(raw);
    if (!m) {
      return { ok: false, err: 'Ingresá un número válido.' };
    }
    var maxInt = parseInt(el.dataset.validarMaxInt || NUM_MAX_INT_DEFAULT, 10);
    var maxDec = parseInt(el.dataset.validarMaxDec || NUM_MAX_DEC_DEFAULT, 10);
    var ints = m[1].replace(/^0+(?=\d)/, '');
    var decs = m[2] || '';
    if (ints.length > maxInt) {
      return {
        ok: false,
        err: 'El número es demasiado grande (máx. ' + maxInt + ' dígitos enteros).',
      };
    }
    if (decs.length > maxDec) {
      return {
        ok: false,
        err: 'El número no puede tener más de ' + maxDec + ' decimales.',
      };
    }
    return { ok: true, raw: raw };
  }

  // ---------- Algoritmos SRI (espejo de app/orders/validators.py) ----------

  function digitoCedula(c) {
    var pesos = [2, 1, 2, 1, 2, 1, 2, 1, 2];
    var suma = 0, i, p;
    for (i = 0; i < 9; i++) {
      p = +c[i] * pesos[i];
      suma += p >= 10 ? p - 9 : p;
    }
    return String((10 - (suma % 10)) % 10);
  }

  function esCedulaValida(c) {
    if (!/^\d{10}$/.test(c)) return false;
    var prov = +c.slice(0, 2);
    if (prov < 1 || prov > 24) return false;
    if ('012345'.indexOf(c[2]) === -1) return false;
    return digitoCedula(c) === c[9];
  }

  function digitoMod11(p, pesos) {
    var suma = 0, i, r;
    for (i = 0; i < 9; i++) suma += +p[i] * pesos[i];
    r = suma % 11;
    return r === 0 ? '0' : (r === 1 ? '1' : String(11 - r));
  }

  function esRucValido(r) {
    if (!/^\d{13}$/.test(r)) return false;
    var t = r[2];
    if (t === '9') return digitoMod11(r, [4, 3, 2, 7, 6, 5, 4, 3, 2]) === r[9];
    if (t === '6') return digitoMod11(r, [3, 2, 7, 6, 5, 4, 3, 2]) === r[9];
    if ('012345'.indexOf(t) > -1) {
      return esCedulaValida(r.slice(0, 10)) && +r.slice(10) >= 1;
    }
    return false;
  }

  function esPasaporteValido(p) {
    return /^[A-Za-z0-9]+$/.test(p) && p.length >= 5 && p.length <= 20;
  }

  // ---------- Utilidades ----------

  function estaOculto(el) {
    return el.offsetParent === null || !!el.closest('.d-none');
  }

  function numeroDe(valor) {
    var n = parseFloat(String(valor).replace(',', '.'));
    return Number.isFinite(n) ? n : NaN;
  }

  function feedbackDe(el, clase) {
    var nodo = el;
    var cont = el.closest('.input-group') || el;
    var prev = cont.parentNode.querySelector('.invalid-feedback, .valid-feedback');
    if (prev) prev.remove();
    el.classList.remove('is-invalid', 'is-valid');
    if (!clase) return null;
    var fb = document.createElement('div');
    fb.className = clase === 'is-invalid' ? 'invalid-feedback' : 'valid-feedback';
    fb.style.display = 'block';
    cont.parentNode.insertBefore(fb, cont.nextSibling);
    el.classList.add(clase);
    return fb;
  }

  // ---------- Validadores ----------

  function validarCampo(el) {
    var tipos = (el.dataset.validar || '').split(/\s+/).filter(Boolean);
    var valor = el.value == null ? '' : String(el.value);
    var errores = [];
    var form = el.form;

    if (estaOculto(el)) return { ok: true, mensaje: '' };

    tipos.forEach(function (t) {
      if (errores.length) return;
      switch (t) {
        case 'requerido':
          if (!valor.trim()) errores.push(MENSAJES.requerido);
          break;
        case 'email':
          if (valor.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(valor.trim())) {
            errores.push(MENSAJES.email);
          }
          break;
        case 'numero':
          if (valor.trim()) {
            var estN = estructuraNumero(el, valor);
            if (!estN.ok) {
              errores.push(estN.err);
            } else {
              var n = numeroDe(valor);
              if (isNaN(n) || n < 0) errores.push(MENSAJES.numero);
            }
          }
          break;
        case 'total':
          if (valor.trim()) {
            var estT = estructuraNumero(el, valor);
            if (!estT.ok) {
              errores.push(estT.err);
            } else {
              var rec = numeroDe(valor);
              var total = numeroDe(el.dataset.validarTotal || '0');
              if (isNaN(rec)) errores.push('Ingresá un monto válido.');
              else if (rec < total) {
                errores.push('El monto recibido no cubre el total ($' + total.toFixed(2) + ').');
              }
            }
          }
          break;
        case 'maxval':
          if (valor.trim()) {
            var estM = estructuraNumero(el, valor);
            if (!estM.ok) {
              errores.push(estM.err);
            } else {
              var v = numeroDe(valor);
              var max = numeroDe(el.dataset.validarMaxVal);
              if (isNaN(v)) errores.push('Ingresá un número válido.');
              else if (!isNaN(max) && v > max) {
                errores.push('No puede ser mayor a $' + max.toFixed(2) + '.');
              }
            }
          }
          break;
        case 'password':
          if (valor) {
            var min = parseInt(el.dataset.validarMin || '8', 10);
            if (valor.length < min) {
              errores.push('La contraseña debe tener al menos ' + min + ' caracteres.');
            } else if (/^\d+$/.test(valor)) {
              errores.push('La contraseña no puede ser solo números.');
            }
          }
          break;
        case 'usuario':
          if (valor.trim() &&
              (!/^[\w.@+-]{3,150}$/.test(valor.trim()))) {
            errores.push(MENSAJES.usuario);
          }
          break;
        case 'cedula':
          if (valor.trim() && !esCedulaValida(valor.trim())) errores.push(MENSAJES.cedula);
          break;
        case 'ruc':
          if (valor.trim() && !esRucValido(valor.trim())) errores.push(MENSAJES.ruc);
          break;
        case 'pasaporte':
          if (valor.trim() && !esPasaporteValido(valor.trim())) errores.push(MENSAJES.pasaporte);
          break;
        case 'identificacion':
          if (valor.trim()) {
            var sel = el.dataset.validarTipo || '';
            var tipo = sel && form ? form.querySelector(sel) : null;
            var t = tipo ? tipo.value : '07';
            if (t === '04' && !esRucValido(valor.trim())) errores.push(MENSAJES.ruc);
            else if (t === '05' && !esCedulaValida(valor.trim())) errores.push(MENSAJES.cedula);
            else if (t === '06' && !esPasaporteValido(valor.trim())) errores.push(MENSAJES.pasaporte);
          }
          break;
        case 'imagen':
          if (el.files && el.files.length) {
            var archivo = el.files[0];
            var nombre = (archivo.name || '').toLowerCase();
            var ext = nombre.indexOf('.') > -1 ? nombre.split('.').pop() : '';
            var permitidas = (el.dataset.validarImagenExt || IMAGEN_EXT_DEFAULT)
              .split(',').map(function (s) { return s.trim(); });
            var maxMb = parseFloat(el.dataset.validarImagenMax || IMAGEN_MAX_DEFAULT);
            if (permitidas.indexOf(ext) === -1) errores.push(MENSAJES.imagen_ext);
            else if (archivo.size > maxMb * 1024 * 1024) {
              errores.push('La imagen supera el máximo de ' + maxMb + ' MB.');
            }
          }
          break;
      }
    });

    return { ok: errores.length === 0, mensaje: errores[0] || '' };
  }

  // ---------- Disponibilidad de usuario (async) ----------

  function chequearDisponibilidad(el, mostrar) {
    var url = el.dataset.validarDisponible;
    var valor = (el.value || '').trim();
    if (!url || !/^[\w.@+-]{3,150}$/.test(valor)) return;

    clearTimeout(el._debounce);
    var token = (el._token = (el._token || 0) + 1);
    el._debounce = setTimeout(function () {
      var req = new XMLHttpRequest();
      req.open('GET', url + (url.indexOf('?') > -1 ? '&' : '?') +
        'username=' + encodeURIComponent(valor));
      req.onload = function () {
        if (token !== el._token) return; // respuesta obsoleta
        var resp = {};
        try { resp = JSON.parse(req.responseText); } catch (e) { /* noop */ }
        var ok = resp.disponible === true;
        if (!mostrar && !ok) return;
        if (ok) {
          feedbackDe(el, 'is-valid').textContent = '✓ ' + DISPONIBLE_OK;
          el._estado = 'ok';
        } else {
          var msg = resp.motivo === 'reservado'
            ? 'Ese nombre de usuario está reservado.'
            : (resp.motivo === 'formato' ? MENSAJES.usuario : DISPONIBLE_ERROR);
          feedbackDe(el, 'is-invalid').textContent = msg;
          el._estado = 'error';
        }
      };
      req.send();
    }, 400);
  }

  // ---------- Estado visual ----------

  function aplicarEstado(el, ok, mensaje, aplicacion) {
    var fb;
    if (ok) {
      fb = feedbackDe(el, 'is-valid');
      if (fb) fb.textContent = '✓ Correcto';
      el._estado = 'ok';
    } else {
      fb = feedbackDe(el, 'is-invalid');
      if (fb) fb.textContent = mensaje;
      el._estado = 'error';
    }
    if (aplicacion) aplicacion();
  }

  function validarEl(el, mostrar) {
    var valor = (el.value == null ? '' : String(el.value)).trim();
    var vacio = !valor;
    var r = validarCampo(el);

    // Vacío y sin tocar: no mostrar nada hasta el blur.
    if (vacio && !mostrar) {
      feedbackDe(el, '');
      el._estado = null;
      return true;
    }
    // Vacío tocado: solo error de obligatorio.
    if (vacio) {
      var tipos = (el.dataset.validar || '').split(/\s+/);
      if (tipos.indexOf('requerido') > -1) {
        aplicarEstado(el, false, MENSAJES.requerido);
      } else {
        feedbackDe(el, '');
        el._estado = null;
      }
      return true;
    }

    aplicarEstado(el, r.ok, r.mensaje);
    if (r.ok) chequearDisponibilidad(el, mostrar);
    return r.ok;
  }

  function validarFormulario(form) {
    var campos = form.querySelectorAll('[data-validar]');
    var primero = null;
    campos.forEach(function (el) {
      if (estaOculto(el)) return;
      var ok = validarEl(el, true);
      if (!ok && !primero) primero = el;
    });
    return primero;
  }

  // ---------- Registro ----------

  function registrar() {
    var forms = document.querySelectorAll('form');
    forms.forEach(function (form) {
      var campos = form.querySelectorAll('[data-validar]');
      if (!campos.length) return;

      campos.forEach(function (el) {
        el._tocado = false;

        el.addEventListener('blur', function () {
          el._tocado = true;
          if (el.dataset.validarDisponible) {
            var valor = (el.value || '').trim();
            if (!/^[\w.@+-]{3,150}$/.test(valor)) {
              validarEl(el, true);
            } else {
              chequearDisponibilidad(el, true);
            }
          } else {
            validarEl(el, true);
          }
        });

        el.addEventListener('input', function () {
          validarEl(el, el._tocado);
        });

        el.addEventListener('change', function () {
          validarEl(el, el._tocado);
        });

        // Revalidar cuando cambia el tipo de identificación u otro campo
        // referenciado por data-validar-tipo. Siempre, incluso si el campo
        // está vacío y sin tocar: así se marca el requerido en tiempo real.
        var selTipo = el.dataset.validarTipo;
        if (selTipo) {
          var ref = form.querySelector(selTipo);
          if (ref) {
            ref.addEventListener('change', function () {
              el._tocado = true;
              validarEl(el, true);
            });
          }
        }
      });

      form.addEventListener('submit', function (e) {
        var primero = validarFormulario(form);
        if (primero) {
          e.preventDefault();
          primero.focus();
        }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', registrar);
  } else {
    registrar();
  }
})();
