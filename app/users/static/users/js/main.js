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

    // ----- Confirm para botones con data-confirm -----
    $('.btn-confirm').on('click', function (e) {
        var msg = $(this).data('confirm') || '¿Estás seguro?';
        if (!confirm(msg)) e.preventDefault();
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
