/* ===== Doña Sara - JS general (Bootstrap 4 + jQuery) ===== */

$(function () {
    // Auto-dismiss de alerts después de 6s
    setTimeout(function () {
        $('.alert:not(.alert-permanent)').fadeOut(400, function () { $(this).remove(); });
    }, 6000);

    // Tooltips
    $('[data-toggle="tooltip"]').tooltip();

    // Confirmación inline para botones con data-confirm
    $('.btn-confirm').on('click', function (e) {
        var msg = $(this).data('confirm') || '¿Estás seguro?';
        if (!confirm(msg)) e.preventDefault();
    });

    // ===== Sidebar mobile: hamburger + backdrop + close button =====
    var $sidebar = $('#accordionSidebar');
    var $backdrop = $('#sidebarBackdrop');
    var $hamburger = $('#sidebarToggleTop');
    var $bottomToggle = $('#sidebarToggle');
    var $closeBtn = $('#sidebarCloseBtn');

    function isMobile() { return window.matchMedia('(max-width: 991.98px)').matches; }

    function showSidebar() {
        $sidebar.addClass('toggled');
        if (isMobile()) {
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
        if ($sidebar.hasClass('toggled')) {
            hideSidebar();
        } else {
            showSidebar();
        }
    }

    // SB Admin 2 trae su propio handler en sb-admin-2.min.js; lo reemplazamos.
    // Quitamos handlers previos para evitar dobles toggles.
    $hamburger.off('click').on('click', function (e) {
        e.preventDefault();
        toggleSidebar();
    });
    $bottomToggle.off('click').on('click', function (e) {
        e.preventDefault();
        toggleSidebar();
    });

    // Click en el backdrop cierra el sidebar
    $backdrop.on('click', hideSidebar);

    // Click en el botón ✕ del sidebar cierra el sidebar
    $closeBtn.on('click', function (e) {
        e.preventDefault();
        hideSidebar();
    });

    // En mobile, click en un link del sidebar cierra el sidebar después de navegar
    $sidebar.on('click', 'a.nav-link[href]:not([href="#"])', function () {
        if (isMobile()) hideSidebar();
    });

    // Cerrar con ESC
    $(document).on('keydown', function (e) {
        if (e.key === 'Escape' && $sidebar.hasClass('toggled') && isMobile()) {
            hideSidebar();
        }
    });

    // Si redimensionan la ventana hacia desktop, sacamos el backdrop
    var resizeTimer;
    $(window).on('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            if (!isMobile()) {
                $backdrop.removeClass('show');
                $('body').css('overflow', '');
            }
        }, 150);
    });
});

// Helper: formatear moneda en pesos
window.formatMoney = function (value) {
    var num = parseFloat(value || 0);
    return '$' + num.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// Helper: leer CSRF token desde cookie
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
