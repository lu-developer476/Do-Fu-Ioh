import json
import random
from copy import deepcopy

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import Deck, DeckEntry, MatchRecord, MonsterCard

HAND_SIZE = 3
DEFAULT_DECK_SIZE = 10
BOARD_WIDTH = 12
BOARD_HEIGHT = 15
MAX_SUMMONS_PER_TURN = 1


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
        'image': f'/static/{card.image}' if card.image else '',
    }


def _serialize_user(user):
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'avatar_url': user.profile.avatar_url,
    }


def index(request):
    return render(request, 'core/index.html')


def health(request):
    return JsonResponse({'status': 'ok', 'game': 'Do-Fu-Ióh', 'timestamp': now().isoformat()})


@require_http_methods(['POST'])
@csrf_exempt
def register_user(request):
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
    logout(request)
    return JsonResponse({'status': 'ok'})


@require_GET
def user_profile(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    _ensure_default_deck(request.user)
    return JsonResponse({'status': 'ok', 'user': _serialize_user(request.user)})


@require_GET
def cards_catalog(request):
    cards = [_serialize_card(c) for c in MonsterCard.objects.all()]
    return JsonResponse({'status': 'ok', 'cards': cards})


def _ensure_default_deck(user):
    if user.decks.exists():
        return user.decks.filter(is_active=True).first() or user.decks.first()
    deck = Deck.objects.create(user=user, name='Mazo inicial', is_active=True)
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


def _create_initial_state(host, guest=None):
    host_deck = _get_active_deck(host)
    guest_deck = _get_active_deck(guest) if guest else None
    return {
        'winner': None,
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


def _summon_rows_for_side(side):
    return {0, 1, 2} if side == 'host' else {BOARD_HEIGHT - 1, BOARD_HEIGHT - 2, BOARD_HEIGHT - 3}


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
    if not request.user.is_authenticated:
        return None, None, None, JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    match = get_object_or_404(MatchRecord, room_code=room_code)
    side = _match_side(match, request.user)
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


@require_http_methods(['POST'])
@csrf_exempt
def create_match(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    _ensure_default_deck(request.user)
    state = _create_initial_state(request.user)
    _start_turn(state, 'host')
    match = MatchRecord.objects.create(host=request.user, game_state=state)
    return JsonResponse({'status': 'ok', 'room_code': match.room_code, 'match': _public_state(match.game_state, 'host')}, status=201)


@require_http_methods(['POST'])
@csrf_exempt
def join_match(request, room_code):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    match = get_object_or_404(MatchRecord, room_code=room_code)
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
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    match = get_object_or_404(MatchRecord, room_code=room_code)
    side = _match_side(match, request.user)
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
    if y not in _summon_rows_for_side(side):
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
