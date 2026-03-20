# Do-Fu-Ióh

MVP actual: **juego táctico single-player contra IA** con Django + sesiones.

## Qué hace hoy

- No hay login/registro para jugar.
- El jugador usa **sesión de Django** como identidad de partida.
- Los usuarios `__solo_player__` y `__dojo_ai__` existen sólo como **actores internos compartidos** para persistir `MatchRecord`; no representan login humano ni ownership real del jugador.
- Botón **“Jugar vs IA”** crea/reinicia una partida para la sesión actual.
- El tablero siempre renderiza (aunque no haya partida activa todavía).
- Estado de partida persistido en `MatchRecord.game_state`.
- Catálogo de cartas cargado desde `data/cards.json` (seed automático si la tabla está vacía).
- El catálogo, la mano y el tablero usan las imágenes reales publicadas en `public/images`.
- Los costos de invocación del MVP dependen de la etapa de la carta: `base=1`, `fusion=3`, `evolution=5`.

## Nota sobre usuarios del sistema del MVP

- Se mantienen porque para el MVP actual resuelven una necesidad concreta: `MatchRecord.host` y `MatchRecord.guest` requieren `User`, pero el producto sigue siendo **single-player por sesión**, sin registro ni autenticación.
- La identidad real del jugador hoy vive en la **sesión de Django** (`active_ai_match_room_code`), no en esas filas de `auth_user`.
- Para reducir rarezas, el código ahora encapsula esos actores en `core/system_users.py`, los trata como usernames reservados, les deja contraseña inutilizable y `is_active=False`.
- Si en el futuro aparece login real, estos usuarios deben seguir reservados o migrarse a un modelo explícito de actores del sistema antes de exponer registro público.

## Endpoints activos

- `GET /` UI del juego.
- `GET /health/` healthcheck.
- `GET /api/cards/` catálogo de cartas.
- `GET /api/match/active/` partida activa asociada a la sesión.
- `POST /api/match/create-vs-ai/` crea/reinicia partida vs IA para la sesión.
- `GET /api/match/<room_code>/` obtiene estado de la partida (solo si coincide con sesión).
- `POST /api/match/<room_code>/action/` acciones: `summon`, `move`, `attack`, `end_turn`.

## Variables de entorno

### Necesarias en Render

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=do-fu-ioh.onrender.com`
- `CSRF_TRUSTED_ORIGINS=https://do-fu-ioh.onrender.com`
- `DATABASE_URL=postgresql://USER:PASSWORD@HOST:6543/postgres`

### Opcional

- `PYTHON_VERSION=3.12.8`
- `DJANGO_SECURE_SSL_REDIRECT=True`

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
export DJANGO_DEBUG=True
export DJANGO_SECRET_KEY=dev-only-secret
python manage.py migrate
python manage.py runserver
```

Abrir: `http://127.0.0.1:8000/`

## Static files

- `STATIC_URL` es `/static/`.
- `STATIC_ROOT` es `.staticfiles/` en la raíz del repo y se genera sólo como artefacto de build.
- `STATICFILES_DIRS` incluye `public/` y `core/static/` aporta los assets por app; todo se resuelve vía `collectstatic`.
- En producción se usa `whitenoise.storage.CompressedManifestStaticFilesStorage`.
- `collectstatic` corre durante el build de Render, antes del deploy.

## Render

Configuración efectiva del deploy:

- **Build Command:** `./build.sh`
- **Pre-Deploy Command:** `python manage.py migrate --noinput --fake-initial`
- **Start Command:** `gunicorn do_fu_ioh.wsgi:application --bind 0.0.0.0:$PORT`

### Qué hace cada paso

1. `build.sh` actualiza `pip`, instala dependencias y ejecuta `python manage.py collectstatic --noinput`.
2. `preDeployCommand` corre las migraciones una vez por deploy, antes de arrancar la nueva versión.
3. `startCommand` sólo inicia Gunicorn, sin mezclar tareas de build o migración.

Esto deja alineados build, migraciones y archivos estáticos con la configuración real de Django y Render. `staticfiles/` no debe versionarse: el código fuente vive en `public/` y `core/static/`, mientras que `.staticfiles/` se reconstruye en cada build con `collectstatic`.
