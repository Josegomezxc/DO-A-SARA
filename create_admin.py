import os
import django

# Configurar el entorno de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'doñaSara.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Pon aquí los datos que tú quieras para tu administrador
USERNAME = 'andres'
EMAIL = 'andres@donasara.com'
PASSWORD = 'chelochelo2004@'  # <-- Cambia esto por la clave que quieras

if not User.objects.filter(username=USERNAME).exists():
    User.objects.create_superuser(username=USERNAME, email=EMAIL, password=PASSWORD)
    print("¡Superusuario creado con éxito!")
else:
    print("El superusuario ya existe, saltando paso.")