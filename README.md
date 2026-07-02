# Do-Fu-Ióh

MVP single-player de combate táctico por turnos contra una IA básica, reconfigurado en **modo sin Backend para la partida**.

## Estado actual

- `GET /` sirve la interfaz y embebe el catálogo desde `data/cards.json`.
- El duelo vs IA corre en el navegador con JavaScript vanilla.
- La partida se guarda en `localStorage` del navegador.
- Las acciones de juego ya no hacen `POST` a Django, Supabase, Postgres ni sesiones HTTP.
- `GET /api/cards/` queda como endpoint informativo/fallback de catálogo seed.
- Las APIs históricas de partida (`/api/match/...`) devuelven `410 Gone` porque el estado de duelo ya no vive en el servidor.

## Por qué

La versión anterior persistía partidas en base de datos y dependía de sesión + backend para crear duelos y resolver acciones. Eso hacía que cualquier problema de base, Supabase o despliegue terminara rompiendo la experiencia con errores 500. Ahora el flujo crítico del juego no requiere backend: si carga la página, se puede jugar.

## Stack real

### Frontend de juego

- Template HTML de Django sólo como shell estático.
- JavaScript vanilla en `core/static/core/js/game.js`.
- Estado local en `localStorage` bajo la clave `do_fu_ioh_backendless_match_v1`.
- Catálogo inicial embebido en el HTML con `json_script` desde `data/cards.json`.

### Servidor mínimo

- Django sigue sirviendo la página, archivos estáticos y salud.
- La base de datos ya no forma parte del camino crítico del juego.
- `GET /health/` reporta modo `backendless` y base de datos `disabled`.

## Funcionalidades disponibles

- Nuevo duelo.
- Barajar cartas.
- Usar selección manual del catálogo para priorizar cartas en mano.
- Invocar cartas en cinco espacios.
- Atacar unidades enemigas.
- Finalizar turno y resolver respuesta automática de la IA.

## Setup local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py runserver
```

Abrí `http://127.0.0.1:8000/` e iniciá un **Nuevo duelo**.

## Tests

```bash
python manage.py test
```
