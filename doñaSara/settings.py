"""
Configuracion Django para el proyecto Doña Sara.
Sistema de gestion de puesto de ventas de papas fritas y hamburguesas.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(key, default=None, cast=str):
    """Lee variable de entorno con cast opcional."""
    val = os.environ.get(key, default)
    if val is None:
        return None
    if cast is bool:
        if isinstance(val, bool):
            return val
        return str(val).lower() in ('1', 'true', 'yes', 'on', 'si', 'sí')
    if cast is int:
        try:
            return int(val)
        except (TypeError, ValueError):
            return default
    if cast == 'list':
        return [v.strip() for v in str(val).split(',') if v.strip()]
    return val


# Cargar .env si existe (sin dependencia externa)
_env_file = BASE_DIR / '.env'
if _env_file.exists():
    for line in _env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())


SECRET_KEY = env(
    'SECRET_KEY',
    'django-insecure-fohrtxpop*pc4oj&jm97#t)z19p(gb3@6ojy2-f)_s)i2k4p_i',
)

DEBUG = env('DEBUG', 'True', cast=bool)

ALLOWED_HOSTS = env('ALLOWED_HOSTS', 'localhost,127.0.0.1', cast='list')


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Apps locales (todas dentro del paquete `app/`)
    'app.users.apps.UsersConfig',
    'app.products.apps.ProductsConfig',
    'app.orders.apps.OrdersConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'doñaSara.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'app.users.context_processors.business_info',
                'app.users.context_processors.topbar_notifs',
            ],
        },
    },
]

WSGI_APPLICATION = 'doñaSara.wsgi.application'


# Base de datos - PostgreSQL si USE_POSTGRES=True, SQLite por defecto
USE_POSTGRES = env('USE_POSTGRES', 'False', cast=bool)

if USE_POSTGRES:
    DATABASES = {
        'default': {
            'ENGINE': env('DB_ENGINE', 'django.db.backends.postgresql'),
            'NAME': env('DB_NAME', 'donasara_db'),
            'USER': env('DB_USER', 'postgres'),
            'PASSWORD': env('DB_PASSWORD', 'postgres'),
            'HOST': env('DB_HOST', 'localhost'),
            'PORT': env('DB_PORT', '5432'),
            'OPTIONS': {
                'connect_timeout': 10,
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 6}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True


# Archivos estaticos
# Cada app aporta sus assets desde app/<nombre>/static/<nombre>/...
# Y el theme SB Admin 2 está en static/sb-admin-2/
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Archivos media
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Autenticacion
LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'users:dashboard'
LOGOUT_REDIRECT_URL = 'users:login'

# Configuracion del negocio
NEGOCIO_NOMBRE = env('NEGOCIO_NOMBRE', 'Doña Sara - Papas y Hamburguesas')
STOCK_MINIMO_ALERTA = env('STOCK_MINIMO_ALERTA', '10', cast=int)

# Mensajes Bootstrap
from django.contrib.messages import constants as messages
MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}



# ─────────────────────────────────────────────────────
# SEGURIDAD — configuración para producción
# ─────────────────────────────────────────────────────

# Protección CSRF
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Sesiones seguras
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 60 * 60 * 8       # 8 horas máximo
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Forzar HTTPS en producción
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

# Cabeceras de seguridad HTTP
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Rate limiting en login — activar en producción:
# 1. pip install django-axes
# 2. Agregar 'axes' a INSTALLED_APPS (antes de django.contrib.auth)
# 3. Agregar 'axes.backends.AxesStandaloneBackend' a AUTHENTICATION_BACKENDS
# 4. Agregar AxesMiddleware al MIDDLEWARE
# AXES_FAILURE_LIMIT = 5          # Bloquear tras 5 intentos fallidos
# AXES_COOLOFF_TIME = 1           # Bloqueo de 1 hora
# AXES_RESET_ON_SUCCESS = True
