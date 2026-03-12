# Do-Fu-Ióh

Proyecto base en **Python + Django + Supabase (Postgres) + Render** para un juego de cartas por turnos.

## Qué trae

- Login / registro con **Django Auth** y sesión.
- Catálogo de monstruos cargado desde `data/cards.json`.
- Imágenes de cartas organizadas por familia y etapa.
- Sistema básico de mazos.
- Partidas online por sala (`room_code`).
- Lógica por turnos con 3 carriles.
- Invocación, movimiento, ataque y fin de turno.
- Persistencia de partidas en `MatchRecord.game_state`.
- Preparado para deploy en Render con base de datos Postgres de Supabase.

## Requisitos

- Python 3.12+
- Cuenta en Render
- Proyecto en Supabase con una base Postgres activa

## Variables de entorno

### Obligatorias en producción

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=tu-app.onrender.com`
- `CSRF_TRUSTED_ORIGINS=https://tu-app.onrender.com`
- `DATABASE_URL=postgresql://USER:PASSWORD@HOST:6543/postgres`

### Opcionales

- `PYTHON_VERSION=3.12.8`

## Start Command

```bash
gunicorn do_fu_ioh.wsgi:application
```

## Build Command

```bash
./build.sh
```

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Notas sobre Supabase

Este proyecto usa **Supabase como Postgres administrado** mediante `DATABASE_URL`.
La autenticación del juego está resuelta con **Django Auth**, que es la opción más estable para este stack en Render sin meter JWTs externos ni pelearte con media docena de edge-cases al pedo.
Si después quieres sumar **Supabase Auth** real, ya tienes una base limpia para hacerlo encima.


## Versión CORE liviana

Este ZIP excluye las imágenes pesadas originales de las cartas para que puedas descargarlo sin errores.
Las rutas fueron reemplazadas por un placeholder liviano en `core/static/core/img/placeholders/card-placeholder.svg`.
Luego podés volver a incorporar los artes definitivos en `core/static/core/img/cards/` o migrarlos a Supabase Storage.
