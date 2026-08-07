# Doña Sara — Sistema POS (Django)

Sistema de gestión para el puesto de ventas de papas fritas y hamburguesas
"Doña Sara": punto de venta (POS), pedidos, catálogo de productos, usuarios
con roles y dashboard de ventas.

## Requisitos

- Python 3.10+
- Dependencias en `requirements.txt`

## Instalación y puesta en marcha

```bash
# 1. Crear y activar el entorno virtual
python -m venv ent_fact
ent_fact\Scripts\activate        # Windows
# source ent_fact/bin/activate   # Linux/macOS

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configuración local
copy .env.example .env           # Windows (ajustá los valores)
# cp .env.example .env           # Linux/macOS

# 4. Migraciones + datos iniciales
python manage.py migrate
python manage.py seed_menu --con-productos   # categorías y menú real

# 5. Crear el dueño del sistema (una sola vez)
python manage.py crear_superowner

# 6. Correr
python manage.py runserver
```

## Configuración

Toda la configuración sensible se lee de variables de entorno o de `.env`
(ver `.env.example`). En **producción** es obligatorio definir:

- `SECRET_KEY` — sin ella la app no arranca (nunca usar la de desarrollo).
- `DEBUG=False`
- `ALLOWED_HOSTS` con el dominio real.

Base de datos: SQLite por defecto; PostgreSQL con `USE_POSTGRES=True`.

## Roles

- **Superowner** (dueño): acceso total, protegido de edición/borrado.
- **Admin**: gestiona productos, categorías, empleados y todos los pedidos.
- **Empleado**: POS y sus propios pedidos (no ve los ajenos).

## Seguridad

- Rate limiting en login (máx. `LOGIN_MAX_ATTEMPTS` intentos, cooldown
  configurable, sin dependencias externas).
- Los tickets y pedidos ajenos son inaccesibles para empleados.
- Pedidos solo editables/completables/cancelables en estado pendiente.
- Media en producción servida solo a usuarios autenticados.

## Tests

```bash
python manage.py test
```
