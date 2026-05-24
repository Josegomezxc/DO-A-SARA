# Guía de Seguridad y Modelo SaaS

## Roles del sistema

| Rol           | Descripción                                        | ¿Editable desde panel? |
|---------------|----------------------------------------------------|------------------------|
| `superowner`  | **Vos** — dueño del SaaS. Acceso total, intocable. | ❌ Nunca               |
| `admin`       | Admin del negocio cliente. Gestiona empleados.     | ✅ Sí                  |
| `empleado`    | Empleado del negocio. Solo opera el sistema.       | ✅ Sí                  |

El `superowner` **no aparece en ninguna lista** del panel de empleados y **nadie puede editarlo, desactivarlo ni eliminarlo** desde la interfaz.

---

## Primer uso — crear tu usuario de propietario

Ejecutá esto **una sola vez** al instalar el sistema:

```bash
python manage.py crear_superowner
```

Te pedirá usuario y contraseña. Guardá esas credenciales en un lugar muy seguro (gestor de contraseñas).

---

## Dar acceso a un cliente (SaaS)

Cuando vendés el sistema a alguien, corrés:

```bash
python manage.py dar_acceso_cliente
```

El comando te pregunta el nombre de usuario y puede **generar una contraseña segura automáticamente**. Luego le enviás esas credenciales al cliente.

**El cliente puede crear sus propios empleados desde el panel, pero vos siempre mantenés el acceso** porque tu usuario `superowner` es invisible e intocable para ellos.

---

## Cambiar tu contraseña de superowner

```bash
python manage.py cambiar_password_superowner
```

---

## Checklist de seguridad antes de vender

### Variables de entorno (`.env`)
```env
SECRET_KEY=genera-una-clave-larga-y-aleatoria-aqui
DEBUG=False
ALLOWED_HOSTS=tudominio.com,www.tudominio.com
USE_POSTGRES=True
DB_PASSWORD=contraseña-fuerte-de-base-de-datos
```

### Generar SECRET_KEY segura
```python
python -c "from django.core.signing import get_cookie_signer; import secrets; print(secrets.token_urlsafe(50))"
```
O simplemente:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### Rate limiting en login (protección contra fuerza bruta)
Instalá `django-axes` para bloquear IPs con muchos intentos fallidos:
```bash
pip install django-axes
```
Luego descomentá las líneas `AXES_*` en `settings.py`.

### Checklist final
- [ ] `DEBUG=False` en producción
- [ ] `SECRET_KEY` cambiada y segura (no la del `.env` de ejemplo)
- [ ] Contraseña de base de datos fuerte
- [ ] HTTPS configurado (las cookies seguras se activan solas con `DEBUG=False`)
- [ ] Superowner creado con contraseña fuerte (mínimo 10 caracteres)
- [ ] `django-axes` instalado y configurado
- [ ] Backups de base de datos programados

---

## ¿Qué pasa si un cliente intenta sacarte el acceso?

**No puede.** Tu usuario `superowner`:
- No aparece en la lista de empleados del panel
- No puede ser editado por ningún usuario desde la interfaz
- No puede ser desactivado desde la interfaz
- La única forma de modificarlo es con acceso directo al servidor (que vos controlás)

Si en algún momento un cliente "hostil" intentara algo, podés desactivar su cuenta con:
```bash
python manage.py shell -c "from django.contrib.auth.models import User; User.objects.filter(username='cliente').update(is_active=False)"
```
