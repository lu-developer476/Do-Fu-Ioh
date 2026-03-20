# Arquitectura técnica de Do-Fu-Ióh

## Objetivo de esta fase

Esta fase deja el proyecto estable para una segunda etapa futura sin ampliar el alcance funcional actual. El juego sigue siendo **single-player vs IA por sesión HTTP**, pero ahora queda con reglas y contratos más explícitos para mantenerlo y extenderlo de forma segura.

## Módulos principales

### `core/views.py`

Responsabilidades actuales:
- exponer endpoints HTML y JSON,
- validar payloads entrantes,
- validar integridad del `game_state`,
- aplicar acciones del jugador,
- ejecutar el turno heurístico de la IA,
- persistir la partida activa.

### `core/card_catalog.py`

Responsabilidades:
- normalizar y serializar cartas,
- resolver rutas de imagen,
- importar catálogo desde `data/cards.json`,
- rechazar seed inválido de forma explícita.

### Persistencia

- `MonsterCard`: catálogo base de cartas.
- `MatchRecord`: snapshot entero del estado de la partida en `game_state`.
- sesión Django: vínculo real entre navegador y partida activa usando `active_ai_match_room_code`.

## Contratos de integridad del estado

El backend ahora trata como inválidos los estados que incumplen cualquiera de estas reglas:
- `hand_count` debe coincidir con el tamaño real de `hand`.
- `library_count` debe coincidir con el tamaño real de `library`.
- no puede haber unidades superpuestas.
- no puede haber `unit.id` duplicados.
- energía, tablero, turnos y campos de cartas/unidades deben conservar tipos válidos.

Esto evita que una corrupción parcial quede silenciosamente persistida y rompa la UI más adelante.

## Extensión recomendada para fase 2

Sin implementarla todavía, el siguiente paso natural sería extraer la lógica de juego desde `core/views.py` a módulos separados, por ejemplo:
- `core/game/validation.py`
- `core/game/actions.py`
- `core/game/ai.py`
- `core/game/serializers.py`
- `core/services/matches.py`

La fase actual ya deja definidos los bordes que conviene mover: parsing, validación, mutación de estado y persistencia.

## Testing base recomendado

Mantener al menos estas capas:
- tests de endpoints principales,
- tests de regresión para acciones (`summon`, `move`, `attack`, `end_turn`),
- tests de validación de estado corrupto,
- tests de seed/import del catálogo.

## Deploy

### Producción
- `build.sh` instala dependencias y ejecuta `collectstatic`.
- `render.yaml` define migraciones previas al deploy y Gunicorn como server.
- `settings.py` endurece cookies, SSL, HSTS y hosts confiables cuando `DEBUG=False`.

### Entorno local
- SQLite sigue siendo el fallback por defecto.
- La configuración sensible se toma desde variables de entorno documentadas en `env.example`.
