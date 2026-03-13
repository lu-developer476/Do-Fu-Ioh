import json
import random
import secrets
import threading
import time
from copy import deepcopy
from pathlib import Path

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import Deck, DeckEntry, MatchRecord, MonsterCard

HAND_SIZE = 5
DEFAULT_DECK_SIZE = 10
BOARD_WIDTH = 11
BOARD_HEIGHT = 11
MAX_SUMMONS_PER_TURN = 1
AI_USERNAME = "__dojo_ai__"
GUEST_HOST_USERNAME = "__guest_player__"
CARDS_SEED_PATH = Path(__file__).resolve().parent.parent / 'data' / 'cards.json'
REQUIRED_GAME_TABLES = {'core_monstercard', 'core_deck', 'core_deckentry', 'core_matchrecord'}
REQUIRED_AUTH_TABLES = {'auth_user', 'django_session'}
_schema_bootstrap_lock = threading.Lock()
_schema_bootstrap_attempted = False
_schema_bootstrap_last_attempt = 0.0
SCHEMA_BOOTSTRAP_RETRY_SECONDS = 15


def _coerce_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_card_image(image):
    raw_image = (image or '').strip()
    if not raw_image:
        return ''
    if raw_image.startswith(('http://', 'https://', '/')):
        return raw_image
    normalized = raw_image[7:] if raw_image.startswith('public/') else raw_image
    return f'/static/{normalized}'


def _payload(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return {}


def _serialize_card(card):
    return {
        'id': card.id,
        'name': card.name,
        'slug': card.slug,
        'family': card.family,
        'stage': card.stage,
        'level_min': card.level_min,
        'level_max': card.level_max,
        'hp': card.hp,
        'shell': card.shell,
        'action_points': card.action_points,
        'movement_points': card.movement_points,
        'description': card.description,
        'image': _resolve_card_image(card.image),
    }


def _serialize_user(user):
    try:
        avatar_url = user.profile.avatar_url
    except ObjectDoesNotExist:
        avatar_url = ''
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'avatar_url': avatar_url,
    }


def _game_schema_is_ready():
    try:
        available_tables = set(connection.introspection.table_names())
    except (OperationalError, ProgrammingError):
        return False
    return REQUIRED_GAME_TABLES.issubset(available_tables)


def _auth_schema_is_ready():
    try:
        available_tables = set(connection.introspection.table_names())
    except (OperationalError, ProgrammingError):
        return False
    return REQUIRED_AUTH_TABLES.issubset(available_tables)


def _try_bootstrap_schema_once():
    global _schema_bootstrap_attempted, _schema_bootstrap_last_attempt

    if _schema_bootstrap_attempted:
        return

    now_ts = time.monotonic()
    if now_ts - _schema_bootstrap_last_attempt < SCHEMA_BOOTSTRAP_RETRY_SECONDS:
        return

    with _schema_bootstrap_lock:
        now_ts = time.monotonic()
        if _schema_bootstrap_attempted:
            return
        if now_ts - _schema_bootstrap_last_attempt < SCHEMA_BOOTSTRAP_RETRY_SECONDS:
            return

        _schema_bootstrap_last_attempt = now_ts

        try:
            call_command('migrate', interactive=False, run_syncdb=True, verbosity=0)
            _schema_bootstrap_attempted = _game_schema_is_ready() and _auth_schema_is_ready()
        except Exception:
            # Si Render no puede migrar en runtime, dejamos que la API responda con 503 amigable.
            pass


def _ensure_schema_ready(include_auth=False):
    game_ready = _game_schema_is_ready()
    auth_ready = _auth_schema_is_ready() if include_auth else True
    if game_ready and auth_ready:
        return True

    _try_bootstrap_schema_once()
    game_ready = _game_schema_is_ready()
    auth_ready = _auth_schema_is_ready() if include_auth else True
    return game_ready and auth_ready


def _schema_not_ready_response():
    return JsonResponse(
        {
            'status': 'error',
            'message': 'La base de datos todavía no está lista. Ejecutá migraciones y reintentá.',
        },
        status=503,
    )


def _bootstrap_cards_if_empty():
    if not _game_schema_is_ready():
        return

    if MonsterCard.objects.exists() or not CARDS_SEED_PATH.exists():
        return

    try:
        cards_seed = json.loads(CARDS_SEED_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return

    for index, raw_card in enumerate(cards_seed):
        raw_name = raw_card.get('name', 'Carta sin nombre')
        raw_slug = raw_card.get('slug') or slugify(raw_name)
        safe_slug = (raw_slug or f'carta-{index + 1}')[:140]
        MonsterCard.objects.update_or_create(
            slug=safe_slug,
            defaults={
                'family': raw_card.get('family', 'Genérica')[:40],
                'name': raw_name[:120],
                'stage': raw_card.get('stage', 'base'),
                'level_min': _coerce_int(raw_card.get('level_min', 1) or 1, 1),
                'level_max': _coerce_int(raw_card.get('level_max', 1) or 1, 1),
                'hp': _coerce_int(raw_card.get('hp', 1) or 1, 1),
                'shell': _coerce_int(raw_card.get('shell', 0) or 0, 0),
                'action_points': _coerce_int(raw_card.get('action_points', 1) or 1, 1),
                'movement_points': _coerce_int(raw_card.get('movement_points', 1) or 1, 1),
                'description': raw_card.get('description', ''),
                'image': raw_card.get('image', ''),
            },
        )




def _get_or_create_system_user(username, email=''):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email, 'password': '!' },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
    return user


def _request_match_side(match, request):
    state = match.game_state or {}
    if request.user.is_authenticated:
        side = _match_side(match, request.user)
        if side:
            return side

    if state.get('mode') == 'vs_ai':
        session_token = request.session.get('ai_match_token')
        if session_token and session_token == state.get('session_token'):
            return 'host'

    return None

def index(request):
    cards_seed = []
    try:
        raw_cards_seed = json.loads(CARDS_SEED_PATH.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        raw_cards_seed = []

    for card in raw_cards_seed:
        cards_seed.append(
            {
                'id': card.get('id') or card.get('slug') or card.get('name', ''),
                'name': card.get('name', 'Carta sin nombre'),
                'slug': card.get('slug') or slugify(card.get('name', 'carta')),
                'family': card.get('family', 'Genérica'),
                'stage': card.get('stage', 'base'),
                'level_min': _coerce_int(card.get('level_min', 1), 1),
                'level_max': _coerce_int(card.get('level_max', 1), 1),
                'hp': _coerce_int(card.get('hp', 1), 1),
                'shell': _coerce_int(card.get('shell', 0), 0),
                'action_points': _coerce_int(card.get('action_points', 1), 1),
                'movement_points': _coerce_int(card.get('movement_points', 1), 1),
                'description': card.get('description', ''),
                'image': _resolve_card_image(card.get('image', '')),
            }
        )

    return render(request, 'core/index.html', {'cards_seed_json': json.dumps(cards_seed, ensure_ascii=False)})


def health(request):
    return JsonResponse({'status': 'ok', 'game': 'Do-Fu-Ióh', 'timestamp': now().isoformat()})


@require_http_methods(['POST'])
@csrf_exempt
def register_user(request):
    if not _ensure_schema_ready(include_auth=True):
        return _schema_not_ready_response()

    data = _payload(request)
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    if len(username) < 3 or len(password) < 6:
        return JsonResponse({'status': 'error', 'message': 'Usuario o contraseña inválidos'}, status=400)
    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse({'status': 'error', 'message': 'El usuario ya existe'}, status=409)
    user = User.objects.create_user(username=username, email=email, password=password)
    login(request, user)
    _ensure_default_deck(user)
    return JsonResponse({'status': 'ok', 'user': _serialize_user(user)}, status=201)


@require_http_methods(['POST'])
@csrf_exempt
def login_user(request):
    if not _ensure_schema_ready(include_auth=True):
        return _schema_not_ready_response()

    data = _payload(request)
    user = authenticate(request, username=(data.get('username') or '').strip(), password=data.get('password') or '')
    if not user:
        return JsonResponse({'status': 'error', 'message': 'Credenciales inválidas'}, status=401)
    login(request, user)
    _ensure_default_deck(user)
    return JsonResponse({'status': 'ok', 'user': _serialize_user(user)})


@require_http_methods(['POST'])
@csrf_exempt
def logout_user(request):
    if not _ensure_schema_ready(include_auth=True):
        return _schema_not_ready_response()

    logout(request)
    return JsonResponse({'status': 'ok'})


@require_GET
def user_profile(request):
    if not _ensure_schema_ready(include_auth=True):
        return _schema_not_ready_response()

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    _ensure_default_deck(request.user)
    return JsonResponse({'status': 'ok', 'user': _serialize_user(request.user)})


@require_GET
def cards_catalog(request):
    if not _ensure_schema_ready():
        return _schema_not_ready_response()

    _bootstrap_cards_if_empty()
    cards = [_serialize_card(c) for c in MonsterCard.objects.all()]
    return JsonResponse({'status': 'ok', 'cards': cards})


def _ensure_default_deck(user):
    if not _ensure_schema_ready():
        return None

    _bootstrap_cards_if_empty()
    deck = user.decks.filter(is_active=True).first() or user.decks.first()
    if not deck:
        deck = Deck.objects.create(user=user, name='Mazo inicial', is_active=True)
    if deck.entries.count() >= HAND_SIZE:
        return deck

    deck.entries.all().delete()
    families = ['Píos', 'Escarahojas', 'Gelatinas', 'Kitsus']
    for family in families:
        family_cards = list(MonsterCard.objects.filter(family=family, stage='base')[:3])
        for card in family_cards:
            DeckEntry.objects.create(deck=deck, card=card, quantity=1)
    keep = list(deck.entries.all()[:DEFAULT_DECK_SIZE])
    deck.entries.exclude(id__in=[entry.id for entry in keep]).delete()
    return deck


def _serialize_deck(deck):
    return {
        'id': deck.id,
        'name': deck.name,
        'is_active': deck.is_active,
        'cards': [
            {**_serialize_card(entry.card), 'quantity': entry.quantity}
            for entry in deck.entries.select_related('card').all()
        ]
    }


@require_http_methods(['GET', 'POST'])
@csrf_exempt
def decks_list_create(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    if request.method == 'GET':
        _ensure_default_deck(request.user)
        decks = [_serialize_deck(d) for d in request.user.decks.prefetch_related('entries__card').all()]
        return JsonResponse({'status': 'ok', 'decks': decks})

    data = _payload(request)
    name = (data.get('name') or 'Nuevo mazo').strip()[:60]
    card_ids = data.get('card_ids') or []
    cards = list(MonsterCard.objects.filter(id__in=card_ids)[:20])
    if len(cards) < 10:
        return JsonResponse({'status': 'error', 'message': 'El mazo necesita al menos 10 cartas'}, status=400)
    deck = Deck.objects.create(user=request.user, name=name, is_active=False)
    for card in cards[:20]:
        DeckEntry.objects.create(deck=deck, card=card, quantity=1)
    return JsonResponse({'status': 'ok', 'deck': _serialize_deck(deck)}, status=201)


@require_http_methods(['GET', 'PATCH', 'DELETE'])
@csrf_exempt
def deck_detail(request, deck_id):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    deck = get_object_or_404(Deck.objects.prefetch_related('entries__card'), id=deck_id, user=request.user)
    if request.method == 'GET':
        return JsonResponse({'status': 'ok', 'deck': _serialize_deck(deck)})
    if request.method == 'DELETE':
        deck.delete()
        return JsonResponse({'status': 'ok'})
    data = _payload(request)
    if data.get('activate'):
        request.user.decks.update(is_active=False)
        deck.is_active = True
        deck.save(update_fields=['is_active'])
    return JsonResponse({'status': 'ok', 'deck': _serialize_deck(deck)})


def _get_active_deck(user):
    return _ensure_default_deck(user)


def _deck_cards(deck):
    cards = []
    for entry in deck.entries.select_related('card').all():
        for _ in range(entry.quantity):
            cards.append(_serialize_card(entry.card))
    random.shuffle(cards)
    return cards


def _new_player_state(user, deck):
    library = _deck_cards(deck)
    hand = library[:HAND_SIZE]
    library = library[HAND_SIZE:]
    return {
        'user_id': user.id,
        'username': user.username,
        'deck_id': deck.id,
        'life': 30,
        'energy': 3,
        'max_energy': 3,
        'hand': hand,
        'library': library,
        'graveyard': [],
    }


def _create_initial_state(host, guest=None, mode='pvp', session_token=''):
    host_deck = _get_active_deck(host)
    guest_deck = _get_active_deck(guest) if guest else None
    return {
        'winner': None,
        'mode': mode,
        'session_token': session_token,
        'board': {'width': BOARD_WIDTH, 'height': BOARD_HEIGHT},
        'turn': {
            'number': 1,
            'active_side': 'host',
            'actions': {
                'summons': 0,
                'draw_used': False,
                'moved_units': [],
                'attacked_units': [],
            },
        },
        'discard': [],
        'units': [],
        'event_log': [
            {
                'turn': 1,
                'event': 'match_created',
                'message': 'Partida creada: tablero 12x15 listo.',
            }
        ],
        'host': _new_player_state(host, host_deck),
        'guest': _new_player_state(guest, guest_deck) if guest else None,
    }


def _match_side(match, user):
    if user.id == match.host_id:
        return 'host'
    if match.guest_id and user.id == match.guest_id:
        return 'guest'
    return None


def _enemy_side(side):
    return 'guest' if side == 'host' else 'host'


def _draw_card(player_state):
    if player_state['library']:
        player_state['hand'].append(player_state['library'].pop(0))


def _manhattan(a_x, a_y, b_x, b_y):
    return abs(a_x - b_x) + abs(a_y - b_y)


def _is_inside_board(x, y):
    return 0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT


def _units_for_side(state, side):
    return [u for u in state['units'] if u['owner'] == side and u['hp_current'] > 0]


def _find_unit(state, unit_id):
    for unit in state['units']:
        if unit['id'] == unit_id:
            return unit
    return None


def _find_unit_by_pos(state, x, y):
    for unit in state['units']:
        if unit['x'] == x and unit['y'] == y and unit['hp_current'] > 0:
            return unit
    return None


def _is_cell_free(state, x, y):
    return _find_unit_by_pos(state, x, y) is None


def _deployment_cells_for_side(side):
    middle_x = BOARD_WIDTH // 2
    if side == 'host':
        return {
            (middle_x, 0),
            (middle_x - 1, 1),
            (middle_x, 1),
            (middle_x + 1, 1),
            (middle_x, 2),
        }
    return {
        (middle_x, BOARD_HEIGHT - 1),
        (middle_x - 1, BOARD_HEIGHT - 2),
        (middle_x, BOARD_HEIGHT - 2),
        (middle_x + 1, BOARD_HEIGHT - 2),
        (middle_x, BOARD_HEIGHT - 3),
    }


def _combat_range(card):
    base = 1 if card['stage'] == 'base' else 2
    return min(5, base + card['action_points'] // 2)


def _combat_damage(card):
    return max(1, card['action_points'] + (card['level_max'] - card['level_min']) // 2)


def _check_winner(match, state):
    if state['host']['life'] <= 0:
        state['winner'] = 'guest'
        match.winner_id = match.guest_id
        match.status = 'finished'
    elif state['guest'] and state['guest']['life'] <= 0:
        state['winner'] = 'host'
        match.winner_id = match.host_id
        match.status = 'finished'


def _start_turn(state, side):
    player = state[side]
    player['max_energy'] = min(10, player['max_energy'] + 1)
    player['energy'] = player['max_energy']
    _draw_card(player)
    for unit in _units_for_side(state, side):
        unit['pm_current'] = unit['card']['movement_points']
        unit['pa_current'] = unit['card']['action_points']
        unit['can_move'] = True
        unit['can_act'] = True

    state['turn']['actions'] = {
        'summons': 0,
        'draw_used': False,
        'moved_units': [],
        'attacked_units': [],
    }


def _require_turn(state, side):
    turn = state['turn']
    return turn['active_side'] == side and not state.get('winner')


def _end_turn(state):
    current_side = state['turn']['active_side']
    next_side = _enemy_side(current_side)
    state['turn']['active_side'] = next_side
    state['turn']['number'] += 1
    _start_turn(state, next_side)


def _serialize_units(state, side):
    return [deepcopy(u) for u in _units_for_side(state, side)]


def _public_state(state, viewer_side):
    public_state = deepcopy(state)
    hidden = _enemy_side(viewer_side)
    public_state.pop('session_token', None)
    public_state['viewer_side'] = viewer_side

    if public_state.get(hidden):
        public_state[hidden]['library_count'] = len(public_state[hidden]['library'])
        public_state[hidden]['hand_count'] = len(public_state[hidden]['hand'])
        public_state[hidden].pop('library', None)
        public_state[hidden].pop('hand', None)

    if public_state.get(viewer_side):
        public_state[viewer_side]['library_count'] = len(public_state[viewer_side]['library'])

    public_state['host']['units'] = _serialize_units(state, 'host')
    if public_state.get('guest'):
        public_state['guest']['units'] = _serialize_units(state, 'guest')

    return public_state


def _safe_int(value, default=-1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _append_event(state, event, message):
    state['event_log'].append({'turn': state['turn']['number'], 'event': event, 'message': message})


def _validate_match_for_action(request, room_code):
    match = get_object_or_404(MatchRecord, room_code=room_code)
    side = _request_match_side(match, request)
    if not side:
        return None, None, None, JsonResponse({'status': 'error', 'message': 'No perteneces a esta sala'}, status=403)
    state = deepcopy(match.game_state)
    if not state.get('guest'):
        return None, None, None, JsonResponse({'status': 'error', 'message': 'Esperando rival'}, status=409)
    if not _require_turn(state, side):
        return None, None, None, JsonResponse({'status': 'error', 'message': 'No es tu turno'}, status=409)
    return match, state, side, None


def _save_and_respond(match, state, side, room_code):
    match.game_state = state
    match.save(update_fields=['game_state', 'status', 'winner', 'updated_at'])
    return JsonResponse({'status': 'ok', 'room_code': room_code, 'match': _public_state(state, side)})


def _free_cell_for_summon(state, side):
    deployment_cells = sorted(_deployment_cells_for_side(side), key=lambda cell: (cell[1], cell[0]), reverse=(side == 'guest'))
    for x, y in deployment_cells:
        if _is_cell_free(state, x, y):
            return x, y
    return None, None


def _run_ai_turn(state):
    if state.get('winner') or state['turn']['active_side'] != 'guest' or not state.get('guest'):
        return

    ai_player = state['guest']
    host_player = state['host']
    actions = state['turn']['actions']

    if ai_player['hand'] and actions['summons'] < MAX_SUMMONS_PER_TURN:
        x, y = _free_cell_for_summon(state, 'guest')
        if x is not None:
            card = ai_player['hand'][0]
            summon_cost = max(1, card['level_min'])
            if ai_player['energy'] >= summon_cost:
                card = ai_player['hand'].pop(0)
                ai_player['energy'] -= summon_cost
                state['units'].append({
                    'id': f"u-{card['slug']}-{random.randint(1000, 9999)}",
                    'base_card_id': card['id'],
                    'owner': 'guest',
                    'x': x,
                    'y': y,
                    'card': card,
                    'hp_current': card['hp'],
                    'shell_current': card['shell'],
                    'pa_current': 0,
                    'pm_current': 0,
                    'status': 'summoned',
                    'can_act': False,
                    'can_move': False,
                    'summoned_turn': state['turn']['number'],
                })
                actions['summons'] += 1
                _append_event(state, 'ai_summon', f"{ai_player['username']} invocó {card['name']} en ({x},{y}).")

    for unit in list(_units_for_side(state, 'guest')):
        if unit['summoned_turn'] == state['turn']['number'] or not unit['can_act'] or unit['pa_current'] <= 0:
            continue
        host_units = _units_for_side(state, 'host')
        in_range = [u for u in host_units if _manhattan(unit['x'], unit['y'], u['x'], u['y']) <= _combat_range(unit['card'])]
        if not in_range:
            continue
        target = sorted(in_range, key=lambda u: (_manhattan(unit['x'], unit['y'], u['x'], u['y']), u['hp_current']))[0]

        damage = _combat_damage(unit['card'])
        unit['pa_current'] -= 1
        unit['can_act'] = unit['pa_current'] > 0
        remaining = damage
        if target['shell_current'] > 0:
            absorbed = min(target['shell_current'], remaining)
            target['shell_current'] -= absorbed
            remaining -= absorbed
        if remaining > 0:
            target['hp_current'] -= remaining

        if target['hp_current'] <= 0:
            host_player['graveyard'].append(target['card'])
            state['discard'].append(target['card'])
            state['units'] = [u for u in state['units'] if u['id'] != target['id']]
            _append_event(state, 'ai_attack', f"{unit['card']['name']} derrotó a {target['card']['name']}.")
        else:
            _append_event(state, 'ai_attack', f"{unit['card']['name']} golpeó a {target['card']['name']} por {damage}.")

    if not state.get('winner'):
        _end_turn(state)
        _append_event(state, 'ai_end_turn', f"{ai_player['username']} terminó su turno.")


@require_http_methods(['POST'])
@csrf_exempt
def create_match(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    if not _ensure_schema_ready(include_auth=True):
        return _schema_not_ready_response()

    _ensure_default_deck(request.user)
    state = _create_initial_state(request.user)
    _start_turn(state, 'host')
    match = MatchRecord.objects.create(host=request.user, game_state=state)
    return JsonResponse({'status': 'ok', 'room_code': match.room_code, 'match': _public_state(match.game_state, 'host')}, status=201)



@require_http_methods(['POST'])
@csrf_exempt
def create_match_vs_ai(request):
    if not _ensure_schema_ready(include_auth=True):
        return _schema_not_ready_response()

    host_user = request.user if request.user.is_authenticated else _get_or_create_system_user(GUEST_HOST_USERNAME)
    ai_user = _get_or_create_system_user(AI_USERNAME)
    _ensure_default_deck(host_user)
    _ensure_default_deck(ai_user)

    session_token = secrets.token_urlsafe(18)
    request.session['ai_match_token'] = session_token
    request.session.save()

    state = _create_initial_state(host_user, ai_user, mode='vs_ai', session_token=session_token)
    state['host']['username'] = request.user.username if request.user.is_authenticated else 'Invitado'
    state['guest']['username'] = 'Do-Fu IA'
    _start_turn(state, 'host')

    match = MatchRecord.objects.create(host=host_user, guest=ai_user, status='in_progress', game_state=state)
    return JsonResponse({'status': 'ok', 'room_code': match.room_code, 'match': _public_state(match.game_state, 'host')}, status=201)


@require_http_methods(['POST'])
@csrf_exempt
def join_match(request, room_code):
    if not _ensure_schema_ready(include_auth=True):
        return _schema_not_ready_response()
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    match = get_object_or_404(MatchRecord, room_code=room_code)
    if match.game_state.get('mode') == 'vs_ai':
        return JsonResponse({'status': 'error', 'message': 'Esta sala es exclusiva para partidas contra IA'}, status=409)
    if match.guest_id and match.guest_id != request.user.id:
        return JsonResponse({'status': 'error', 'message': 'La sala ya está llena'}, status=409)
    if match.host_id == request.user.id:
        return JsonResponse({'status': 'ok', 'room_code': match.room_code, 'match': _public_state(match.game_state, 'host')})
    match.guest = request.user
    match.status = 'in_progress'
    state = _create_initial_state(match.host, request.user)
    _start_turn(state, 'host')
    match.game_state = state
    match.save(update_fields=['guest', 'status', 'game_state', 'updated_at'])
    return JsonResponse({'status': 'ok', 'room_code': match.room_code, 'match': _public_state(match.game_state, 'guest')})


@require_GET
def get_match(request, room_code):
    match = get_object_or_404(MatchRecord, room_code=room_code)
    side = _request_match_side(match, request)
    if not side:
        return JsonResponse({'status': 'error', 'message': 'No perteneces a esta sala'}, status=403)
    return JsonResponse({'status': 'ok', 'room_code': room_code, 'match': _public_state(match.game_state, side)})


@require_http_methods(['POST'])
@csrf_exempt
def draw_card(request, room_code):
    match, state, side, error = _validate_match_for_action(request, room_code)
    if error:
        return error

    actions = state['turn']['actions']
    if actions['draw_used']:
        return JsonResponse({'status': 'error', 'message': 'Ya robaste carta en este turno'}, status=400)
    player = state[side]
    if not player['library']:
        return JsonResponse({'status': 'error', 'message': 'No quedan cartas en el mazo'}, status=400)

    _draw_card(player)
    actions['draw_used'] = True
    _append_event(state, 'draw_card', f"{player['username']} robó una carta.")
    return _save_and_respond(match, state, side, room_code)


@require_http_methods(['POST'])
@csrf_exempt
def summon_unit(request, room_code):
    match, state, side, error = _validate_match_for_action(request, room_code)
    if error:
        return error

    data = _payload(request)
    hand_index = _safe_int(data.get('hand_index'))
    x = _safe_int(data.get('x'))
    y = _safe_int(data.get('y'))
    player = state[side]
    actions = state['turn']['actions']

    if actions['summons'] >= MAX_SUMMONS_PER_TURN:
        return JsonResponse({'status': 'error', 'message': 'Ya invocaste el máximo permitido este turno'}, status=400)
    if hand_index < 0 or hand_index >= len(player['hand']):
        return JsonResponse({'status': 'error', 'message': 'Carta inválida'}, status=400)
    if not _is_inside_board(x, y):
        return JsonResponse({'status': 'error', 'message': 'Casilla fuera del tablero'}, status=400)
    if (x, y) not in _deployment_cells_for_side(side):
        return JsonResponse({'status': 'error', 'message': 'Solo puedes invocar en tu zona de despliegue'}, status=400)
    if not _is_cell_free(state, x, y):
        return JsonResponse({'status': 'error', 'message': 'Casilla ocupada'}, status=400)

    card = player['hand'][hand_index]
    summon_cost = max(1, card['level_min'])
    if player['energy'] < summon_cost:
        return JsonResponse({'status': 'error', 'message': 'No te alcanza la energía'}, status=400)

    card = player['hand'].pop(hand_index)
    player['energy'] -= summon_cost
    state['units'].append({
        'id': f"u-{card['slug']}-{random.randint(1000, 9999)}",
        'base_card_id': card['id'],
        'owner': side,
        'x': x,
        'y': y,
        'card': card,
        'hp_current': card['hp'],
        'shell_current': card['shell'],
        'pa_current': 0,
        'pm_current': 0,
        'status': 'summoned',
        'can_act': False,
        'can_move': False,
        'summoned_turn': state['turn']['number'],
    })
    actions['summons'] += 1
    _append_event(state, 'summon', f"{player['username']} invocó {card['name']} en ({x},{y}).")
    return _save_and_respond(match, state, side, room_code)


@require_http_methods(['POST'])
@csrf_exempt
def move_unit(request, room_code):
    match, state, side, error = _validate_match_for_action(request, room_code)
    if error:
        return error

    data = _payload(request)
    unit = _find_unit(state, data.get('unit_id'))
    to_x = _safe_int(data.get('to_x'))
    to_y = _safe_int(data.get('to_y'))

    if not unit or unit['owner'] != side:
        return JsonResponse({'status': 'error', 'message': 'Unidad inválida'}, status=400)
    if unit['hp_current'] <= 0 or not unit['can_move']:
        return JsonResponse({'status': 'error', 'message': 'La unidad no puede moverse'}, status=400)
    if unit['summoned_turn'] == state['turn']['number']:
        return JsonResponse({'status': 'error', 'message': 'La unidad no puede moverse el turno en que fue invocada'}, status=400)
    if not _is_inside_board(to_x, to_y):
        return JsonResponse({'status': 'error', 'message': 'Destino fuera del tablero'}, status=400)
    if not _is_cell_free(state, to_x, to_y):
        return JsonResponse({'status': 'error', 'message': 'Casilla ocupada'}, status=400)

    distance = _manhattan(unit['x'], unit['y'], to_x, to_y)
    if distance <= 0:
        return JsonResponse({'status': 'error', 'message': 'Movimiento nulo'}, status=400)
    if distance > unit['pm_current']:
        return JsonResponse({'status': 'error', 'message': 'No puedes mover más allá del PM disponible'}, status=400)

    unit['x'] = to_x
    unit['y'] = to_y
    unit['pm_current'] -= distance
    unit['can_move'] = unit['pm_current'] > 0
    state['turn']['actions']['moved_units'].append(unit['id'])
    _append_event(state, 'move', f"{unit['card']['name']} se movió a ({to_x},{to_y}).")
    return _save_and_respond(match, state, side, room_code)


@require_http_methods(['POST'])
@csrf_exempt
def attack_unit(request, room_code):
    match, state, side, error = _validate_match_for_action(request, room_code)
    if error:
        return error

    data = _payload(request)
    attacker = _find_unit(state, data.get('attacker_id'))
    target = _find_unit(state, data.get('target_id'))
    enemy = state[_enemy_side(side)]

    if not attacker or attacker['owner'] != side:
        return JsonResponse({'status': 'error', 'message': 'Atacante inválido'}, status=400)
    if not target or target['owner'] == side:
        return JsonResponse({'status': 'error', 'message': 'Objetivo inválido'}, status=400)
    if attacker['summoned_turn'] == state['turn']['number']:
        return JsonResponse({'status': 'error', 'message': 'La unidad no puede atacar el turno en que fue invocada'}, status=400)
    if not attacker['can_act'] or attacker['pa_current'] <= 0:
        return JsonResponse({'status': 'error', 'message': 'La unidad no puede actuar'}, status=400)

    distance = _manhattan(attacker['x'], attacker['y'], target['x'], target['y'])
    if distance > _combat_range(attacker['card']):
        return JsonResponse({'status': 'error', 'message': 'No puedes atacar fuera del rango permitido'}, status=400)

    damage = _combat_damage(attacker['card'])
    attacker['pa_current'] -= 1
    attacker['can_act'] = attacker['pa_current'] > 0
    state['turn']['actions']['attacked_units'].append(attacker['id'])

    remaining = damage
    if target['shell_current'] > 0:
        absorbed = min(target['shell_current'], remaining)
        target['shell_current'] -= absorbed
        remaining -= absorbed
    if remaining > 0:
        target['hp_current'] -= remaining

    if target['hp_current'] <= 0:
        enemy['graveyard'].append(target['card'])
        state['discard'].append(target['card'])
        state['units'] = [u for u in state['units'] if u['id'] != target['id']]
        _append_event(state, 'attack', f"{attacker['card']['name']} derrotó a {target['card']['name']}.")
    else:
        _append_event(state, 'attack', f"{attacker['card']['name']} golpeó a {target['card']['name']} por {damage}.")

    return _save_and_respond(match, state, side, room_code)


@require_http_methods(['POST'])
@csrf_exempt
def end_turn(request, room_code):
    match, state, side, error = _validate_match_for_action(request, room_code)
    if error:
        return error

    player = state[side]
    _end_turn(state)
    _append_event(state, 'end_turn', f"{player['username']} terminó su turno.")

    if state.get('mode') == 'vs_ai' and state['turn']['active_side'] == 'guest':
        _run_ai_turn(state)

    return _save_and_respond(match, state, side, room_code)


@require_http_methods(['POST'])
@csrf_exempt
def match_action(request, room_code):
    data = _payload(request)
    action = data.get('action')
    if action == 'draw_card':
        return draw_card(request, room_code)
    if action == 'summon':
        return summon_unit(request, room_code)
    if action == 'move':
        return move_unit(request, room_code)
    if action == 'attack':
        return attack_unit(request, room_code)
    if action == 'end_turn':
        return end_turn(request, room_code)
    return JsonResponse({'status': 'error', 'message': 'Acción desconocida'}, status=400)
