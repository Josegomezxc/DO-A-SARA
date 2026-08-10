(function () {
    'use strict';

    var OJO = 'fa-eye';
    var OJO_TACHADO = 'fa-eye-slash';

    function alternar(selector) {
        var input = document.querySelector(selector);
        if (!input) return;
        var esTexto = input.type === 'text';
        input.type = esTexto ? 'password' : 'text';
        return !esTexto; // true si ahora es visible
    }

    document.addEventListener('click', function (e) {
        var boton = e.target.closest('[data-toggle-password]');
        if (!boton) return;
        e.preventDefault();
        var visible = alternar(boton.dataset.togglePassword);
        var icono = boton.querySelector('.fa-eye, .fa-eye-slash');
        if (icono) {
            icono.classList.remove(OJO, OJO_TACHADO);
            icono.classList.add(visible ? OJO_TACHADO : OJO);
        }
        boton.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
        boton.title = visible ? 'Ocultar contraseña' : 'Mostrar contraseña';
    });
})();
