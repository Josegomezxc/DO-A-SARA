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
