/* ===== Doña Sara — JS general (Bootstrap 4 + jQuery) =====
   Maneja:
   - Toggle del sidebar (mobile + tablet + desktop)
   - Backdrop, botón ✕, tecla ESC, click en link, click outside
   - Botón scroll-to-top
   - Auto-dismiss de alerts
   - Helpers globales (formatMoney, getCsrfToken)
   No usamos sb-admin-2.min.js porque tenía un handler que abría el
   sidebar solo al hacer scroll en mobile (resize <480px).
============================================================= */

$(function () {

    // ----- Auto-dismiss de alerts después de 6s -----
    setTimeout(function () {
        $('.alert:not(.alert-permanent)').fadeOut(400, function () { $(this).remove(); });
    }, 6000);

    // ----- Tooltips -----
    $('[data-toggle="tooltip"]').tooltip();

    // ----- Confirmación para acciones riesgosas (modal Bootstrap 4) -----
    // Elementos con .btn-confirm abren #confirmModal en vez del confirm() nativo.
    // Atributos opcionales:
    //   data-confirm           -> mensaje del popup
    //   data-confirm-titulo    -> título del popup
    //   data-confirm-boton     -> texto del botón de acción
    //   data-confirm-clase     -> clase del botón (btn-danger | btn-warning)
    //   data-confirm-icono     -> ícono FontAwesome del botón de acción
    //   data-confirm-url       -> si está, al aceptar hace POST a esa URL (con CSRF)
    //   data-confirm-form      -> si está y el trigger está dentro de un <form>,
    //                             al aceptar hace submit de ese form
    $('.btn-confirm').on('click', function (e) {
        e.preventDefault();
        var $btn = $(this);
        window.mostrarConfirmacion({
            titulo: $btn.data('confirm-titulo'),
            mensaje: $btn.data('confirm'),
            boton: $btn.data('confirm-boton'),
            clase: $btn.data('confirm-clase'),
            icono: $btn.data('confirm-icono'),
            url: $btn.data('confirm-url'),
            form: $btn.closest('form')[0] || null,
        });
    });

    // ===== Sidebar: hamburger + backdrop + close button + ESC =====
    var $sidebar = $('#accordionSidebar');
    var $backdrop = $('#sidebarBackdrop');
    var $hamburger = $('#sidebarToggleTop');
    var $bottomToggle = $('#sidebarToggle');
    var $closeBtn = $('#sidebarCloseBtn');

    // Mobile y tablet: < 992px (Bootstrap lg breakpoint)
    function isMobileOrTablet() {
        return window.matchMedia('(max-width: 991.98px)').matches;
    }

    function showSidebar() {
        $sidebar.addClass('toggled');
        if (isMobileOrTablet()) {
            $backdrop.addClass('show');
            $('body').css('overflow', 'hidden');
        }
    }

    function hideSidebar() {
        $sidebar.removeClass('toggled');
        $backdrop.removeClass('show');
        $('body').css('overflow', '');
    }

    function toggleSidebar() {
        if ($sidebar.hasClass('toggled')) hideSidebar();
        else showSidebar();
    }

    $hamburger.on('click', function (e) { e.preventDefault(); toggleSidebar(); });
    $bottomToggle.on('click', function (e) { e.preventDefault(); toggleSidebar(); });
    $backdrop.on('click', hideSidebar);
    $closeBtn.on('click', function (e) { e.preventDefault(); hideSidebar(); });

    // Click en un link del sidebar (mobile/tablet) → cerrar
    $sidebar.on('click', 'a.nav-link[href]:not([href="#"])', function () {
        if (isMobileOrTablet()) hideSidebar();
    });

    // Tecla ESC cierra el sidebar abierto
    $(document).on('keydown', function (e) {
        if (e.key === 'Escape' && $sidebar.hasClass('toggled') && isMobileOrTablet()) {
            hideSidebar();
        }
    });

    // Al redimensionar A desktop (>= 992px), sacar backdrop y body lock
    var resizeTimer;
    $(window).on('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            if (!isMobileOrTablet()) {
                $backdrop.removeClass('show');
                $('body').css('overflow', '');
            }
        }, 150);
    });
    // IMPORTANTE: NO agregamos auto-toggle del sidebar al resizear.
    // SB Admin 2 lo hacía y causaba que el sidebar se abriera solo
    // al hacer scroll en mobile (porque el browser dispara resize al
    // mostrar/ocultar la barra de URL).


    // ===== Scroll-to-top button =====
    var $scrollTop = $('.scroll-to-top');

    $(document).on('scroll', function () {
        if ($(this).scrollTop() > 100) $scrollTop.fadeIn(150);
        else $scrollTop.fadeOut(150);
    });

    $scrollTop.on('click', function (e) {
        e.preventDefault();
        var href = $(this).attr('href') || '#page-top';
        var $target = $(href).length ? $(href) : $('html, body');
        $('html, body').stop().animate({
            scrollTop: $target === $('html, body') ? 0 : $target.offset().top
        }, 600);
    });

    // Estado inicial: ocultar el scroll-to-top si estamos arriba
    if ($(document).scrollTop() <= 100) $scrollTop.hide();
});


// ===== Helpers globales =====

window.formatMoney = function (value) {
    var num = parseFloat(value || 0);
    return '$' + num.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

window.getCsrfToken = function () {
    // Con CSRF_COOKIE_HTTPONLY=True la cookie no es legible por JS; el token
    // se expone en <meta name="csrf-token"> en base.html (fallback a la cookie).
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;

    var name = 'csrftoken';
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
        var c = cookies[i].trim();
        if (c.indexOf(name + '=') === 0) {
            return decodeURIComponent(c.substring(name.length + 1));
        }
    }
    return '';
};

// ===== Confirmación genérica para acciones riesgosas =====
// window.mostrarConfirmacion({titulo, mensaje, boton, clase, icono, url, form, alAceptar})
//   - url: POST a esa URL (con CSRF) al aceptar
//   - form: submit de ese formulario al aceptar
//   - alAceptar: función callback al aceptar (prioridad sobre url/form)
window.mostrarConfirmacion = function (opciones) {
    opciones = opciones || {};
    var $modal = $('#confirmModal');
    if (!$modal.length) return false;

    $('#confirmModalLabel').text(opciones.titulo || '¿Confirmar acción?');
    $('#confirmModalMensaje').text(opciones.mensaje || '¿Estás seguro?');

    var $btn = $('#confirmModalBtn');
    $btn.removeClass('btn-danger btn-warning btn-primary').addClass(opciones.clase || 'btn-danger');
    var icono = opciones.icono ? '<i class="' + opciones.icono + ' fa-sm fa-fw" aria-hidden="true"></i> ' : '';
    $btn.html(icono + (opciones.boton || 'Confirmar'));

    $modal.data('pendiente', opciones);
    $modal.addClass('show');
    $modal.attr('aria-hidden', 'false');
    return true;
};

// Ocultar el popup de confirmación
function ocultarConfirmacion() {
    $('#confirmModal').removeClass('show').attr('aria-hidden', 'true');
}

// Cancelar / cerrar (✕ o tecla ESC)
$(document).on('click', '#confirmModalCancelar, #confirmModalCerrar', ocultarConfirmacion);
$(document).on('keydown', function (e) {
    if (e.key === 'Escape') ocultarConfirmacion();
});

// Al aceptar: ejecutar la acción pendiente
$(document).on('click', '#confirmModalBtn', function () {
    var opciones = $('#confirmModal').data('pendiente') || {};
    ocultarConfirmacion();

    if (typeof opciones.alAceptar === 'function') {
        opciones.alAceptar();
        return;
    }
    if (opciones.form) {
        opciones.form.submit();
        return;
    }
    if (opciones.url) {
        var $f = $('<form method="post" action="' + opciones.url + '"></form>')
            .css('display', 'none');
        $('<input type="hidden" name="csrfmiddlewaretoken">')
            .val(window.getCsrfToken())
            .appendTo($f);
        $f.appendTo('body').submit();
    }
});
