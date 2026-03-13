# Do-Fu-Ióh

Proyecto en **Python + Django + Supabase (Postgres) + Render** para un juego táctico por turnos.

## MVP actual (tablero táctico)

- Login / registro con **Django Auth** y sesión.
- Catálogo de cartas (`MonsterCard`) cargado desde `data/cards.json`.
- Sistema de mazos por usuario.
- Partidas por sala (`room_code`) persistidas en `MatchRecord.game_state`.
- **Tablero táctico 12x15** con unidades posicionadas por coordenadas.
- Mano visible e invocación desde carta a zona válida de despliegue.
- Selección de unidad propia sobre el tablero.
- Movimiento por PM y ataque por rango/PA contra objetivos válidos.
- Flujo de turnos por jugador (sin tiempo real / sin WebSockets).
- UI con estado de turno, stats, selección y log de eventos.

## Requisitos

- Python 3.12+
- Cuenta en Render
- Proyecto en Supabase con Postgres activa

## Variables de entorno

### Obligatorias en producción

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=tu-app.onrender.com`
- `CSRF_TRUSTED_ORIGINS=https://tu-app.onrender.com`
- `DATABASE_URL=postgresql://USER:PASSWORD@HOST:6543/postgres`

### Opcionales

- `PYTHON_VERSION=3.12.8`

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata  # opcional si usás fixtures propias
python manage.py runserver
```

Abrir: `http://127.0.0.1:8000/`

## Deploy en Render

Este repo ya está preparado para deploy:

- **Build Command**
  ```bash
  ./build.sh
  ```
- **Start Command**
  ```bash
  gunicorn do_fu_ioh.wsgi:application --bind 0.0.0.0:$PORT
  ```

`render.yaml` incluye configuración base para web service. Solo definí las variables de entorno y `DATABASE_URL` apuntando a Supabase.

### Errores frecuentes (Render + Supabase)

Si ves el mensaje: `La base de datos todavía no está lista. Faltan tablas del juego (...)`, revisá esto:

1. **Variables sin prefijo repetido**
   - En Render, en el campo **Value**, cargá solo el valor.
   - Correcto: `https://do-fu-ioh.onrender.com`
   - Incorrecto: `CSRF_TRUSTED_ORIGINS=https://do-fu-ioh.onrender.com`

2. **DATABASE_URL de Supabase (pooler) bien formada**
   - Formato esperado: `postgresql://USER:PASSWORD@HOST:6543/postgres`

3. **Migraciones ejecutadas**
   - Abrí Shell en Render y corré:
     ```bash
     python manage.py migrate --noinput
     ```

4. **Schema público en Supabase**
   - Verificá en SQL Editor:
     ```sql
     select schemaname, tablename from pg_tables where schemaname='public' order by tablename;
     ```
   - Deben existir tablas como `django_migrations`, `core_monstercard`, `core_deck`, `core_deckentry`, `core_matchrecord`.

## Notas de arquitectura

- Backend y frontend están orientados a **cartas -> invocación -> unidades tácticas**.
- La lógica de lanes/lineal fue desplazada por el flujo de tablero táctico.
- El juego sigue siendo estrictamente por turnos, apto para MVP deployable.
