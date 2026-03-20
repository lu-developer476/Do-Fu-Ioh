# Do-Fu-Ióh

Es un **MVP single-player de combate táctico por turnos contra una IA básica**, hecho con Django y una UI server-rendered con JavaScript vanilla. Sin matchmaking real, PvP online y login obligatorio: el juego corre como una partida asociada a la **sesión HTTP actual**.

## Estado actual del proyecto

### Qué está implementado hoy

- Una pantalla principal en `GET /` con tablero, mano, catálogo y log de eventos.
- Creación/reinicio de una partida **vs IA** usando la sesión actual.
- Estado persistido en base de datos dentro de `MatchRecord.game_state`.
- Catálogo de cartas servido desde la tabla `MonsterCard`.
- Acciones reales disponibles del jugador: **invocar, mover, atacar y terminar turno**.
- Resolución automática del turno enemigo con una **IA heurística básica**.
- Reglas mínimas de energía, movimiento, ataque, robo y condición de victoria.
- Deploy preparado para Render con Gunicorn, WhiteNoise y Postgres.

## Stack real

### Backend

- **Python 3.12** en Render por configuración sugerida del proyecto.
- **Django 5** como framework web principal.
- **Gunicorn** como servidor de aplicación en producción.
- **dj-database-url** para leer `DATABASE_URL`.
- **psycopg 3** para Postgres.
- **SQLite** como fallback local si no se define `DATABASE_URL`.

### Frontend

- Template HTML de Django.
- **JavaScript vanilla** para consumir la API del juego y actualizar tablero / mano.
- **CSS propio** sin framework de UI.
- Assets estáticos servidos con **WhiteNoise** en producción.

### Persistencia y assets

- Modelo `MonsterCard` para catálogo de cartas.
- Modelo `MatchRecord` para guardar el estado de cada partida.
- Estado de “quién está jugando” guardado en la sesión con `active_ai_match_room_code`.
- Imágenes publicadas desde `public/` y resueltas como `/static/...`.

## Cómo funciona el juego hoy

## Modo de juego actual

El único modo implementado es:

- **Jugador vs IA**.
- El jugador siempre actúa como `host`.
- La IA siempre actúa como `guest`.
- La partida activa se recupera por **sesión**, no por usuario autenticado.
- Si la sesión ya tiene una partida activa, el endpoint de creación la **reinicia**.

En la base existen usuarios reservados del sistema (`__solo_player__` y `__dojo_ai__`) para satisfacer las foreign keys de `MatchRecord`, pero **no representan cuentas reales de juego**.

## Reglas actuales del MVP

### Invocación

- Cada jugador arranca con **1 energía / 1 energía máxima**.
- Cada turno, al recibir el control, el jugador activo:
  - aumenta su `max_energy` en 1 hasta un máximo de **10**,
  - recupera energía al máximo,
  - roba 1 carta,
  - refresca movimiento y ataque de sus unidades.
- Sólo se puede hacer **1 invocación por turno**.
- La carta debe salir de la mano y entrar a una casilla libre de la zona de despliegue propia.
- Costos reales de invocación por etapa:
  - `base = 1`
  - `fusion = 3`
  - `evolution = 5`
- Si no alcanza la energía, la invocación falla.

### Movimiento

- El tablero actual es de **11 x 11**.
- El movimiento es ortogonal, por casillas.
- Cada unidad usa sus `movement_points` como PM iniciales del turno.
- El sistema calcula celdas alcanzables con búsqueda sobre el tablero y **no permite atravesar unidades**.
- No se puede mover a una casilla ocupada ni fuera del tablero.
- Una unidad puede seguir moviéndose mientras conserve PM; cuando se queda sin PM, ya no puede moverse ese turno.

### Ataque

- Una unidad puede atacar sólo si todavía tiene PA (`pa_current > 0`) y `can_act = true`.
- Cada ataque consume **1 PA**.
- El rango real depende de la carta:
  - cartas `base`: rango base 1,
  - cartas `fusion` y `evolution`: rango base 2,
  - luego se suma `action_points // 2`, con tope total en **5**.
- El objetivo debe estar dentro del rango Manhattan permitido.
- El daño actual se calcula como `action_points + 2` del atacante.
- Primero se absorbe parte del golpe con `shell_current` del objetivo, y luego se descuenta vida.
- Si la vida llega a 0 o menos, la unidad se elimina del tablero.

### Turnos

- La partida empieza en **turno 1** con `host` activo.
- El jugador humano puede ejecutar estas acciones:
  - `summon`
  - `move`
  - `attack`
  - `end_turn`
- Cuando el jugador termina turno, la IA juega automáticamente y luego devuelve el control al jugador.
- El número de turno aumenta cuando el control vuelve a `host`.
- El log de partida conserva los **últimos 12 eventos**.

### Condición de victoria

La partida termina cuando uno de los lados se queda sin recursos para seguir jugando.

A efectos del MVP, un lado **sigue vivo** si todavía tiene al menos uno de estos recursos:

- unidades en tablero,
- cartas en mano,
- cartas en biblioteca.

Por lo tanto:

- si sólo un lado conserva recursos, ese lado gana;
- si ambos se quedan sin recursos a la vez, gana el lado que ejecutó la acción que disparó esa resolución.

### IA básica

La IA actual no usa árbol de búsqueda ni simulación profunda. Hace una secuencia heurística simple:

1. Si puede, intenta **invocar** una carta pagable en una casilla válida de su zona.
2. Recorre sus unidades.
3. Si una unidad puede atacar, prioriza un objetivo según una heurística.
4. Si no, intenta **moverse hacia el enemigo más cercano** con una evaluación simple de distancia, amenaza y progreso.
5. Después del movimiento vuelve a intentar atacar.
6. Si nadie ganó, ejecuta `end_turn`.

Además hay dos dificultades aceptadas por el backend:

- `normal`
- `extremo`

`extremo` usa prioridades un poco más agresivas para elegir invocaciones, desplazamientos y objetivos, pero sigue siendo una IA simple basada en reglas.

## Endpoints reales

### UI y salud

- `GET /` → renderiza la interfaz del juego.
- `GET /health/` → devuelve `{ "ok": true }`.

### Catálogo

- `GET /api/cards/` → devuelve el catálogo actual de `MonsterCard` serializado.

### Partida activa por sesión

- `GET /api/match/active/` → devuelve la partida activa asociada a la sesión actual, o `match: null` si no hay una.
- `POST /api/match/create-vs-ai/` → crea o reinicia la partida vs IA de la sesión.
  - body opcional: `{ "difficulty": "normal" }` o `{ "difficulty": "extremo" }`

### Partida puntual

- `GET /api/match/<room_code>/` → devuelve el estado de la partida sólo si ese `room_code` coincide con la sesión actual.
- `POST /api/match/<room_code>/action/` → ejecuta una acción del jugador humano.

Acciones soportadas hoy:

- `summon`
  ```json
  {
    "action": "summon",
    "hand_index": 0,
    "x": 5,
    "y": 0
  }
  ```
- `move`
  ```json
  {
    "action": "move",
    "unit_id": "abc123",
    "to_x": 5,
    "to_y": 1
  }
  ```
- `attack`
  ```json
  {
    "action": "attack",
    "attacker_id": "abc123",
    "target_id": "enemy456"
  }
  ```
- `end_turn`
  ```json
  {
    "action": "end_turn"
  }
  ```

### Restricciones reales de acceso

- No podés leer ni accionar una partida ajena: el backend valida que el `room_code` coincida con el almacenado en la sesión actual.
- Las acciones `POST` requieren CSRF válido.

## Setup local

### 1. Crear entorno e instalar dependencias

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Configurar variables mínimas

```bash
export DJANGO_DEBUG=True
export DJANGO_SECRET_KEY=dev-only-secret
```

Si querés usar SQLite local, no hace falta definir `DATABASE_URL`.

### 3. Migrar base

```bash
python manage.py migrate
```

### 4. Cargar catálogo de cartas

```bash
python manage.py seed_cards_catalog
```

Esto carga o actualiza las cartas desde `data/cards.json`.

> Importante: hoy el catálogo **no se siembra automáticamente** al levantar la app ni al consultar `/api/cards/`. Si no corrés este comando, la UI puede abrir pero no va a haber cartas utilizables.

### 5. Levantar el server

```bash
python manage.py runserver
```

Abrí `http://127.0.0.1:8000/`.

## Deploy en Render

La configuración real del repo usa:

- **Build Command:** `./build.sh`
- **Pre-Deploy Command:** `python manage.py migrate --noinput --fake-initial`
- **Start Command:** `gunicorn do_fu_ioh.wsgi:application --bind 0.0.0.0:$PORT`

### Qué hace cada paso

#### Build

`build.sh`:

1. actualiza `pip`,
2. instala `requirements.txt`,
3. elimina artefactos estáticos previos (`staticfiles` y `.staticfiles`),
4. corre `python manage.py collectstatic --noinput`.

#### Pre-deploy

- Ejecuta migraciones antes de arrancar la nueva versión.

#### Start

- Arranca Gunicorn sobre la app Django WSGI.

## Variables de entorno

### Requeridas en producción

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DATABASE_URL`

### Recomendadas para Render

- `DJANGO_ALLOWED_HOSTS=do-fu-ioh.onrender.com`
- `CSRF_TRUSTED_ORIGINS=https://do-fu-ioh.onrender.com`
- `DJANGO_SECURE_SSL_REDIRECT=True`

### Opcionales

- `PYTHON_VERSION=3.12.8`

### Comportamiento actual de configuración

- Si `DATABASE_URL` no existe, Django usa `sqlite:///db.sqlite3`.
- Si `DEBUG=False` y falta `DJANGO_SECRET_KEY`, la app falla al arrancar.
- `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` se completan con defaults razonables para Render y localhost.
- `STATIC_ROOT` es `.staticfiles/`.
- En producción los estáticos usan `CompressedManifestStaticFilesStorage` de WhiteNoise.

## Limitaciones actuales

- El juego real es **solo vs IA**.
- La identidad del jugador depende de la sesión del navegador; no existe cuenta persistente real.
- El modelo `Deck` existe en datos, pero **no forma parte del flujo jugable actual**.
- El catálogo depende de haber cargado `data/cards.json` con el comando de seed.
- No hay efectos de cartas, hechizos, buffs, zonas especiales ni reglas avanzadas.
- Las etapas `fusion` y `evolution` hoy impactan principalmente en costo y rango base, no en mecánicas más profundas.
- La IA es funcional pero simple: no planifica varios turnos ni optimiza de manera sofisticada.
- No hay guardado de historial de partidas consumible desde UI.
- No hay observadores, replay ni analíticas.
- No hay tests end-to-end de navegador; la cobertura actual está concentrada en backend/reglas.

### Qué no está implementado hoy

- Login o registro para jugar.
- PvP entre dos personas.
- Matchmaking, salas compartidas o invitaciones.
- Construcción/edición de mazos desde la UI.
- Efectos complejos de cartas, habilidades especiales o evoluciones en partida.
- Tiempo real, websockets o sincronización multiusuario.

## Próximos pasos sugeridos

1. **Alinear modelos con el producto actual**: separar mejor actores del sistema, sesión de juego y futuros usuarios reales.
2. **Sembrado inicial más claro**: correr `seed_cards_catalog` en un flujo explícito de bootstrap o deploy para evitar catálogos vacíos.
3. **Documentar/estabilizar el contrato JSON** de `match` para poder iterar frontend sin romper integraciones.
4. **Agregar construcción de mazos real** o eliminar temporalmente del dominio las piezas que todavía no participan del MVP.
5. **Expandir reglas de combate**: efectos de carta, tipos de alcance, habilidades activas/pasivas, cooldowns, etc.
6. **Mejorar IA**: priorización más consistente, evaluación de trades y objetivos de victoria.
7. **Agregar autenticación** si el roadmap vuelve a incluir perfiles, progreso o PvP.
8. **Preparar multiplayer real** recién después de estabilizar reglas y estado de partida.
9. **Agregar observabilidad**: logs de errores, métricas básicas y trazabilidad de acciones de partida.
10. **Sumar tests de UI** para validar flujo completo desde el navegador.

## Calidad técnica incorporada en esta pasada

- Validación explícita de integridad para `game_state`, incluyendo conteos, ids duplicados y unidades superpuestas.
- Manejo claro de `JSON inválido` en endpoints críticos.
- Persistencia más consistente del resultado final de la partida en `MatchRecord.status` y `MatchRecord.winner`.
- Import del catálogo más estricto frente a seeds mal formados.
- Tests de regresión para parsing inválido y estados inconsistentes.

## Documentación adicional

- Arquitectura técnica y bordes de extensión futura: `docs/architecture.md`.

## Comandos útiles

```bash
python manage.py migrate
python manage.py seed_cards_catalog
python manage.py test
python manage.py runserver
```
