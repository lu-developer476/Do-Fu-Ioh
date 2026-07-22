# Dofus Duelists

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.x-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![JavaScript](https://img.shields.io/badge/JavaScript-Vanilla-F7DF1E?logo=javascript&logoColor=black)](https://developer.mozilla.org/es/docs/Web/JavaScript)
[![HTML5](https://img.shields.io/badge/HTML5-Templates-E34F26?logo=html5&logoColor=white)](https://developer.mozilla.org/es/docs/Web/HTML)
[![CSS3](https://img.shields.io/badge/CSS3-Responsive-1572B6?logo=css3&logoColor=white)](https://developer.mozilla.org/es/docs/Web/CSS)
[![SQLite](https://img.shields.io/badge/SQLite-Dev-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Prod%20opcional-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Render](https://img.shields.io/badge/Render-Deploy-46E3B7?logo=render&logoColor=black)](https://render.com/)
[![Gunicorn](https://img.shields.io/badge/Gunicorn-WSGI-499848?logo=gunicorn&logoColor=white)](https://gunicorn.org/)
[![WhiteNoise](https://img.shields.io/badge/WhiteNoise-Static%20files-111111)](https://whitenoise.readthedocs.io/)

**Dofus Duelists** es un prototipo web de combate táctico por turnos inspirado en criaturas, cartas coleccionables y duelos contra IA. El proyecto está construido con Django como servidor liviano y una experiencia de juego que corre principalmente en el navegador con JavaScript vanilla.

La prioridad actual del repositorio es que el juego sea **jugable, portable y resistente a fallos de backend**: la página entrega el catálogo de cartas, los recursos estáticos y los endpoints informativos, pero el duelo contra la IA se crea, resuelve y persiste del lado del cliente.

## Estado actual del proyecto

El proyecto se encuentra en estado de **MVP jugable backendless-first**: Django sigue siendo la capa de entrega, configuración, catálogo y operación, mientras que el duelo contra IA se ejecuta y persiste en el navegador. La prioridad actual es mantener una experiencia single-player estable aunque la base de datos o las APIs históricas de partida no estén disponibles.

### Snapshot funcional

- `GET /` sirve la aplicación web y embebe el catálogo inicial desde `data/cards.json`.
- El combate contra IA corre en el navegador, sin depender de `POST` a Django para resolver turnos.
- La partida activa se guarda en `localStorage` con la clave `do_fu_ioh_backendless_match_v3`.
- El backend conserva endpoints de catálogo y salud para operación, diagnóstico y compatibilidad.
- Las APIs históricas de partida existen en las URLs, pero responden `410 Gone` porque el estado de duelo ya no se persiste en servidor.
- El catálogo seed contiene **83 cartas** distribuidas en **7 familias**: Blops, Kitsus, Gelatinas, Escarahojas, Píos, Jalatos y Dragones.
- La distribución actual del catálogo es de **38 cartas base**, **9 fusiones** y **36 evoluciones**.
- Hay assets gráficos versionados en `public/images/` y placeholders locales para cartas sin imagen.
- El despliegue objetivo está preparado para Render con Gunicorn, WhiteNoise, `collectstatic`, migraciones y seed de catálogo.

### Stack tecnológico

| Capa | Tecnología | Uso en el proyecto |
| --- | --- | --- |
| Backend | Python 3.12 + Django 5.x | Servir HTML, catálogo, healthcheck, admin/modelos y rutas legacy. |
| Frontend | JavaScript vanilla, HTML templates y CSS | Motor del duelo, UI, persistencia local, animaciones y audio básico sin bundler. |
| Datos | `data/cards.json` + modelos Django | Seed canónico del catálogo y base para importación/persistencia futura. |
| Persistencia local | `localStorage` | Estado real de la partida activa backendless. |
| Base de datos | SQLite en desarrollo, PostgreSQL opcional en producción | Migraciones, admin, catálogo importado y evolución futura. |
| Estáticos | WhiteNoise + `public/images/` | Entrega de CSS, JS, imágenes y artefactos de `collectstatic`. |
| Producción | Render + Gunicorn | Deploy declarativo del servicio web Python. |
| Testing | Django test runner | Validación de catálogo, endpoints backendless y comportamiento operativo. |

## Qué significa “backendless” en este proyecto

En este repositorio, “backendless” no significa que no exista servidor. Significa que el **camino crítico de la partida** no depende del servidor una vez cargada la página.

Django todavía cumple funciones importantes:

1. Servir el HTML principal.
2. Servir archivos estáticos mediante WhiteNoise en producción.
3. Inyectar el catálogo de cartas validado desde el seed JSON.
4. Exponer `/health/` para monitoreo.
5. Exponer `/api/cards/` como fuente JSON informativa del catálogo.
6. Mantener modelos y comandos de importación para una futura fase con persistencia real.

El navegador se encarga de:

1. Crear una nueva partida.
2. Guardar y restaurar la partida local.
3. Resolver invocaciones, movimiento, ataques, fusiones, evoluciones, turnos y respuesta de la IA.
4. Renderizar tablero, mano, catálogo, bestiario, registro de combate, feedback visual y audio básico.

Este enfoque evita que una caída de base de datos, una sesión inválida o una configuración incompleta de Postgres rompan el duelo contra IA.

## Funcionalidades principales

### Experiencia de juego

- Duelo single-player contra IA.
- Flujo guiado de preparación de partida.
- Selección de cartas desde el catálogo antes de iniciar.
- Filtros por familia y etapa.
- Bestiario integrado con estadísticas, imágenes, descripciones y hechizos.
- Mano inicial configurable.
- Tablero táctico de 13 × 9 casillas.
- Zonas de despliegue por bando.
- Invocación de monstruos.
- Movimiento por puntos de movimiento.
- Ataques y hechizos con rango, coste de PA y daño.
- Escudo o `PdE` como absorción/defensa.
- Puntos de vida o `PdV`.
- Regeneración parcial de escudo según familia y etapa.
- Registro de combate persistido en la partida local.
- Efectos visuales y sonidos generados en el cliente.
- Condición de victoria/derrota cuando un bando queda sin recursos relevantes.

### Reglas de cartas implementadas en cliente

El catálogo distingue tres etapas:

- `base`: criaturas iniciales.
- `fusion`: criaturas generadas por recetas de fusión.
- `evolution`: formas evolucionadas o superiores.

El cliente incluye recetas explícitas para familias como:

- **Píos**: combinaciones y evolución hacia Píoloro.
- **Kitsus**: fusiones Kumiawase, Nishiki, Penta y Yin Yang, con evoluciones asociadas.
- **Escarahojas**: fusiones duocromada, mecanizada, tricolor y variopinta, con evolución hacia Escarasubjefe Bronce.

> Nota: el sistema de reglas es un MVP funcional. No pretende ser todavía un motor completo y separado de reglas; gran parte de la lógica vive en `core/static/core/js/game.js`.

## Catálogo de cartas

La fuente canónica de datos es:

```text
data/cards.json
```

Cada carta puede incluir:

- nombre y `slug`,
- familia,
- etapa,
- nivel mínimo y máximo,
- puntos de vida (`hp`, `hp_min`, `hp_max`),
- escudo (`shell`),
- puntos de acción (`action_points`),
- puntos de movimiento (`movement_points`),
- descripción,
- imagen,
- lista de hechizos.

`core/card_catalog.py` normaliza esos datos, resuelve rutas de imágenes y genera una copia defensiva del seed para que el frontend no dependa de la base de datos.

## Arquitectura

```text
.
├── core/
│   ├── static/core/js/game.js        # Motor y UI del duelo en cliente
│   ├── static/core/css/styles.css    # Estilos de la aplicación
│   ├── templates/core/index.html     # Shell HTML servido por Django
│   ├── card_catalog.py               # Carga, validación y serialización del catálogo
│   ├── views.py                      # Vistas HTML, healthcheck y APIs informativas/legacy
│   ├── models.py                     # Modelos para catálogo, decks y partidas históricas/futuras
│   └── management/commands/          # Comandos operativos, incluido seed de catálogo
├── data/cards.json                   # Catálogo seed versionado
├── public/images/                    # Imágenes estáticas de cartas y favicon
├── do_fu_ioh/settings.py             # Configuración Django
├── do_fu_ioh/urls.py                 # Rutas públicas
├── build.sh                          # Build para Render/producción
├── render.yaml                       # Configuración declarativa de Render
├── env.example                       # Variables de entorno de ejemplo
└── requirements.txt                  # Dependencias Python
```

### Backend Django

El backend está reducido a una capa de entrega y soporte:

- `index`: renderiza la UI e inserta el catálogo seed como JSON seguro.
- `health`: responde modo `backendless` y marca la base como no crítica.
- `cards_catalog`: devuelve el catálogo seed serializado.
- endpoints `/api/match/...`: conservados para compatibilidad de URL, pero deshabilitados con `410 Gone`.

Aunque `core/views.py` conserva funciones históricas de validación y mutación de partidas, las vistas públicas de partida apuntan al handler backendless deshabilitado. Esto facilita una futura recuperación del backend de partidas sin bloquear el estado actual.

### Frontend

La UI de juego está implementada con JavaScript vanilla:

- no hay React, Vue ni bundler;
- no hay paso de build de frontend;
- el archivo principal es servido como estático;
- el estado se serializa en `localStorage`;
- la restauración de partida ocurre al recargar la página si existe estado local válido.

### Persistencia

Actualmente hay dos niveles:

1. **Persistencia real de la partida actual:** `localStorage` del navegador.
2. **Persistencia disponible para futuro/backend:** modelos Django (`MonsterCard`, `Deck`, `DeckEntry`, `MatchRecord`) y migraciones existentes.

En producción, la base de datos puede seguir usándose para migraciones, admin o seed del catálogo, pero no es requisito para jugar una vez cargada la aplicación.

## Endpoints

| Método | Ruta | Uso actual |
| --- | --- | --- |
| `GET` | `/` | Interfaz principal del juego. |
| `GET` | `/health/` | Healthcheck JSON. |
| `GET` | `/api/cards/` | Catálogo seed serializado. |
| `GET` | `/api/match/active/` | Legacy, devuelve `410 Gone`. |
| `POST` | `/api/match/create-vs-ai/` | Legacy, devuelve `410 Gone`. |
| `GET` | `/api/match/<room_code>/` | Legacy, devuelve `410 Gone`. |
| `POST` | `/api/match/<room_code>/action/` | Legacy, devuelve `410 Gone`. |

## Requisitos

- Python 3.12 recomendado.
- pip.
- Entorno virtual de Python.
- SQLite para desarrollo local por defecto.
- PostgreSQL opcional en producción mediante `DATABASE_URL`.

Dependencias principales:

- Django 5.x.
- WhiteNoise.
- Gunicorn.
- dj-database-url.
- psycopg.

## Configuración local

1. Clonar el repositorio.
2. Crear y activar un entorno virtual.
3. Instalar dependencias.
4. Crear archivo `.env` o exportar variables si se desea personalizar configuración.
5. Ejecutar migraciones si se va a usar admin/base local.
6. Levantar el servidor.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

En Windows, la activación del entorno suele ser:

```powershell
.venv\Scripts\activate
```

Luego abrir:

```text
http://127.0.0.1:8000/
```

## Variables de entorno

`env.example` documenta los valores esperados:

| Variable | Descripción |
| --- | --- |
| `DJANGO_SECRET_KEY` | Secreto de Django. En producción debe ser único y privado. |
| `DJANGO_DEBUG` | Activa/desactiva modo debug. |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos separados por coma. |
| `CSRF_TRUSTED_ORIGINS` | Orígenes confiables para CSRF. |
| `DJANGO_SECURE_SSL_REDIRECT` | Fuerza redirección HTTPS si se configura en `True`. |
| `DATABASE_URL` | URL de base de datos; por defecto puede ser SQLite. |
| `PYTHON_VERSION` | Versión sugerida por plataforma de deploy. |

## Comandos útiles

### Ejecutar tests

```bash
python manage.py test
```

### Validar configuración de Django

```bash
python manage.py check
```

### Cargar o actualizar catálogo en base de datos

```bash
python manage.py seed_cards_catalog
```

### Recolectar estáticos

```bash
python manage.py collectstatic --noinput
```

## Deploy

El repositorio incluye configuración para Render:

- `render.yaml` define el servicio web Python.
- `build.sh` instala dependencias, descarga los binarios reales de Git LFS si el checkout dejó punteros en `public/images/`, y ejecuta `collectstatic`.
- `preDeployCommand` ejecuta migraciones y seed del catálogo.
- `gunicorn do_fu_ioh.wsgi:application` sirve la app en producción.

La carpeta `.staticfiles/` es el artefacto único de `collectstatic` y se regenera en build.

### Imágenes y Git LFS

Las imágenes de cartas viven en `public/images/` y están versionadas con Git LFS. Si las cartas se ven rotas en local, Codespaces, Render o GitLab, el checkout probablemente contiene punteros de texto de Git LFS en vez de los archivos PNG reales.

Para arreglar un entorno local o Codespaces:

```bash
git lfs install
git lfs pull
python manage.py collectstatic --noinput
```

Para replicar el repo en GitLab y desplegar en Render desde GitLab, asegurate de migrar también los objetos de Git LFS, no solo el historial Git normal. El build falla con un mensaje explícito si todavía detecta punteros LFS en `public/images/`, para evitar publicar imágenes corruptas.

## Tests existentes

La suite actual cubre especialmente el catálogo y reglas de datos:

- JSON inválido en el seed.
- Copias defensivas del catálogo serializado.
- Refresco de caché cuando cambia el archivo seed.
- Estadísticas de familias concretas.
- Hechizos esperados para Escarahojas y Kitsus.
- Importación/normalización del catálogo hacia modelos.
- Healthcheck y endpoints backendless principales.

## Límites conocidos

- El motor de juego todavía vive en un único archivo JavaScript grande.
- La IA es heurística, no adaptativa.
- El estado local no se sincroniza entre dispositivos ni navegadores.
- Si se borra el `localStorage`, se pierde la partida activa.
- Las APIs de partida del backend están deshabilitadas a propósito.
- Los modelos de `Deck` y `MatchRecord` existen como base para evolución futura, pero no gobiernan el MVP actual.

## Roadmap sugerido

1. Separar el motor de reglas del renderizado en módulos JavaScript.
2. Agregar tests unitarios para reglas de cliente.
3. Documentar formalmente cada familia, hechizo, estado y fórmula de daño.
4. Definir si la fase 2 vuelve a persistir partidas en backend o mantiene un modo offline-first.
5. Extraer recetas de fusión/evolución a datos versionados en lugar de hardcodearlas en JS.
6. Agregar selector de dificultad de IA con diferencias reales de estrategia.
7. Implementar export/import de partidas locales.

## Licencia

Este proyecto incluye un archivo `LICENSE`. Revisalo antes de reutilizar código, datos o assets fuera del repositorio.

## Mirror automático GitHub → GitLab

El repo incluye un workflow de GitHub Actions que replica cada push de GitHub hacia GitLab. Para activarlo, crear en GitHub un secret de Actions llamado `GITLAB_TOKEN` con un Personal Access Token de GitLab que tenga permiso `write_repository` sobre `lu-developer476/Monster-Duelists`.

El workflow no descarga Git LFS desde GitHub; replica las referencias Git para evitar bloquearse cuando GitHub LFS excede la cuota gratuita.
