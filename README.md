# Do-Fu-Ióh

MVP actual: **juego táctico single-player contra IA** con Django + sesiones.

## Qué hace hoy

- No hay login/registro para jugar.
- El jugador usa **sesión de Django** como identidad de partida.
- Botón **“Jugar vs IA”** crea/reinicia una partida para la sesión actual.
- El tablero siempre renderiza (aunque no haya partida activa todavía).
- Estado de partida persistido en `MatchRecord.game_state`.
- Catálogo de cartas cargado desde `data/cards.json` (seed automático si la tabla está vacía).
- El catálogo, la mano y el tablero usan las imágenes reales publicadas en `public/images`.
- Los costos de invocación del MVP dependen de la etapa de la carta: `base=1`, `fusion=3`, `evolution=5`.

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

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DJANGO_DEBUG=True
export DJANGO_SECRET_KEY=dev-only-secret
python manage.py migrate
python manage.py runserver
```

Abrir: `http://127.0.0.1:8000/`

## Render

- **Build Command:** `./build.sh`
- **Start Command:** `python manage.py migrate --noinput --fake-initial && gunicorn do_fu_ioh.wsgi:application --bind 0.0.0.0:$PORT`

`build.sh` instala dependencias y ejecuta `collectstatic`. Las migraciones corren al iniciar el servicio web en Render.
