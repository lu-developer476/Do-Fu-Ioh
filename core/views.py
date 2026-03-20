import json
import random
import secrets
import unicodedata
from collections import deque
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.db.utils import OperationalError, ProgrammingError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods

from .models import MatchRecord, MonsterCard

BOARD_WIDTH = 11
BOARD_HEIGHT = 11
HAND_SIZE = 5
DECK_SIZE = 12
MAX_ENERGY = 10
SESSION_MATCH_KEY = 'active_ai_match_room_code'
AI_USERNAME = '__dojo_ai__'
SOLO_SYSTEM_USERNAME = '__solo_player__'
CARDS_DATA_PATH = Path(settings.BASE_DIR) / 'data' / 'cards.json'
SUMMON_COST_BY_STAGE = {
    'base': 1,
    'fusion': 3,
    'evolution': 5,
}


def _slugify(value: str) -> str:
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = ''.join(ch.lower() if ch.isalnum() else '-' for ch in value)
    return '-'.join(part for part in value.split('-') if part)[:140]


def _payload(request):
    try:
        return json.loads((request.body or b'{}').decode('utf-8'))
    except json.JSONDecodeError:
        return {}


def _json_error(message, status=400):
    return JsonResponse({'ok': False, 'message': message}, status=status)


def _resolve_card_image(image):
    raw = (image or '').strip()
    if not raw:
        return ''
    if raw.startswith(('http://', 'https://', '/')):
        return raw
    cleaned = raw[7:] if raw.startswith('public/') else raw
    return f'/static/{cleaned}'


def _summon_cost(card_like):
    stage = card_like.get('stage', 'base')
    return SUMMON_COST_BY_STAGE.get(stage, 1)


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
        'summon_cost': _summon_cost({'stage': card.stage}),
    }


def _ensure_cards_seeded():
    if not CARDS_DATA_PATH.exists():
        return

    try:
        if MonsterCard.objects.exists():
            return
    except (ProgrammingError, OperationalError):
        return

    cards = json.loads(CARDS_DATA_PATH.read_text(encoding='utf-8'))
    for item in cards:
        MonsterCard.objects.update_or_create(
            slug=_slugify(item['name']),
            defaults={
                'family': item['family'],
                'name': item['name'],
                'stage': item['stage'],
                'level_min': item['level_min'],
                'level_max': item['level_max'],
                'hp': item['hp'],
                'shell': item['shell'],
                'action_points': item['action_points'],
                'movement_points': item['movement_points'],
                'description': item.get('description', ''),
                'image': item.get('image', ''),
            },
        )


def _player_state(side, deck_cards):
    random.shuffle(deck_cards)
    hand = deck_cards[:HAND_SIZE]
    library = deck_cards[HAND_SIZE:]
    return {
        'side': side,
        'energy': 1,
        'max_energy': 1,
        'hand': hand,
        'library': library,
        'library_count': len(library),
        'hand_count': len(hand),
        'units': [],
        'summons_this_turn': 0,
    }


def _build_deck(serialized_cards):
    if not serialized_cards:
        return []
    base_cards = [card for card in serialized_cards if card['stage'] == 'base']
    non_base_cards = [card for card in serialized_cards if card['stage'] != 'base']
    guaranteed = random.choices(base_cards or serialized_cards, k=min(HAND_SIZE, DECK_SIZE))
    remaining_pool = non_base_cards or serialized_cards
    weights = [2 if card['stage'] == 'fusion' else 1 for card in remaining_pool]
    remaining = random.choices(remaining_pool, weights=weights, k=max(0, DECK_SIZE - len(guaranteed)))
    deck = guaranteed + remaining
    random.shuffle(deck)
    return deck


def _build_new_match_state(cards):
    serialized = [_serialize_card(card) for card in cards]
    if not serialized:
        return {
            'mode': 'vs_ai',
            'board': {'width': BOARD_WIDTH, 'height': BOARD_HEIGHT},
            'turn': {'number': 1, 'active_side': 'host'},
            'host': _player_state('host', []),
            'guest': _player_state('guest', []),
            'winner': None,
            'log': ['No hay cartas cargadas en la base de datos.'],
        }

    host_deck = _build_deck(serialized)
    guest_deck = _build_deck(serialized)
    return {
        'mode': 'vs_ai',
        'board': {'width': BOARD_WIDTH, 'height': BOARD_HEIGHT},
        'turn': {'number': 1, 'active_side': 'host'},
        'host': _player_state('host', host_deck),
        'guest': _player_state('guest', guest_deck),
        'winner': None,
        'log': ['Partida iniciada: jugador vs IA.'],
    }


def _get_or_create_system_user(username):
    user, _ = User.objects.get_or_create(username=username, defaults={'email': ''})
    if not user.has_usable_password():
        return user
    user.set_unusable_password()
    user.save(update_fields=['password'])
    return user


def _draw_one(player):
    if not player['library']:
        return
    player['hand'].append(player['library'].pop(0))
    player['library_count'] = len(player['library'])
    player['hand_count'] = len(player['hand'])


def _in_bounds(x, y, width, height):
    return 0 <= x < width and 0 <= y < height


def _deployment_cells(side, width, height):
    center = width // 2
    if side == 'host':
        return {(center, 0), (center - 1, 1), (center, 1), (center + 1, 1), (center, 2)}
    return {
        (center, height - 1),
        (center - 1, height - 2),
        (center, height - 2),
        (center + 1, height - 2),
        (center, height - 3),
    }


def _find_unit(player, unit_id):
    for unit in player['units']:
        if unit['id'] == unit_id:
            return unit
    return None


def _occupied(state, x, y):
    return any(u['x'] == x and u['y'] == y for u in state['host']['units'] + state['guest']['units'])


def _occupied_positions(state, ignore_unit_id=None):
    positions = set()
    for unit in state['host']['units'] + state['guest']['units']:
        if ignore_unit_id and unit['id'] == ignore_unit_id:
            continue
        positions.add((unit['x'], unit['y']))
    return positions


def _reachable_cells(state, unit):
    max_steps = unit.get('pm_current', 0)
    if not unit.get('can_move') or max_steps <= 0:
        return {}

    width = state['board']['width']
    height = state['board']['height']
    blocked = _occupied_positions(state, ignore_unit_id=unit['id'])
    origin = (unit['x'], unit['y'])
    distances = {origin: 0}
    queue = deque([origin])

    while queue:
        cx, cy = queue.popleft()
        current_distance = distances[(cx, cy)]
        if current_distance >= max_steps:
            continue

        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not _in_bounds(nx, ny, width, height) or (nx, ny) in blocked:
                continue

            next_distance = current_distance + 1
            if next_distance > max_steps:
                continue

            previous = distances.get((nx, ny))
            if previous is None or next_distance < previous:
                distances[(nx, ny)] = next_distance
                queue.append((nx, ny))

    distances.pop(origin, None)
    return distances


def _serialize_reachable_cells(state, unit):
    return [
        {'x': x, 'y': y, 'distance': distance}
        for (x, y), distance in sorted(
            _reachable_cells(state, unit).items(),
            key=lambda item: (item[1], item[0][1], item[0][0]),
        )
    ]


def _state_for_client(state):
    payload = json.loads(json.dumps(state))
    for side in ('host', 'guest'):
        for unit in payload.get(side, {}).get('units', []):
            unit['reachable_cells'] = _serialize_reachable_cells(payload, unit)
    return payload


def _can_attack(attacker, target):
    if attacker['pa_current'] <= 0 or not attacker['can_act']:
        return False
    base_range = 1 if attacker['card']['stage'] == 'base' else 2
    attack_range = min(5, base_range + attacker['card']['action_points'] // 2)
    distance = abs(attacker['x'] - target['x']) + abs(attacker['y'] - target['y'])
    return distance <= attack_range


def _refresh_counts(state):
    for side in ('host', 'guest'):
        state[side]['library_count'] = len(state[side]['library'])
        state[side]['hand_count'] = len(state[side]['hand'])


def _reset_turn_state(player):
    player['summons_this_turn'] = 0
    for unit in player['units']:
        unit['pa_current'] = unit['card']['action_points']
        unit['pm_current'] = unit['card']['movement_points']
        unit['can_act'] = True
        unit['can_move'] = True


def _distance(a, b):
    return abs(a['x'] - b['x']) + abs(a['y'] - b['y'])


def _apply_action(state, side, payload):
    if state['winner']:
        return 'La partida ya terminó.'

    if state['turn']['active_side'] != side:
        return 'No es tu turno.'

    action = payload.get('action')
    actor = state[side]
    enemy_side = 'guest' if side == 'host' else 'host'
    enemy = state[enemy_side]
    width = state['board']['width']
    height = state['board']['height']

    if action == 'summon':
        hand_index = payload.get('hand_index')
        x, y = payload.get('x'), payload.get('y')
        if not isinstance(hand_index, int) or hand_index < 0 or hand_index >= len(actor['hand']):
            return 'Carta inválida.'
        if not isinstance(x, int) or not isinstance(y, int) or not _in_bounds(x, y, width, height):
            return 'Casilla inválida.'
        if (x, y) not in _deployment_cells(side, width, height):
            return 'Sólo podés invocar en tu zona azul.'
        if _occupied(state, x, y):
            return 'Esa casilla ya está ocupada.'
        if actor['summons_this_turn'] >= 1:
            return 'Ya invocaste este turno.'

        card = actor['hand'].pop(hand_index)
        cost = _summon_cost(card)
        if actor['energy'] < cost:
            actor['hand'].insert(hand_index, card)
            return 'No alcanza la energía para invocar.'
        actor['energy'] -= cost
        actor['summons_this_turn'] += 1
        actor['units'].append({
            'id': secrets.token_hex(6),
            'owner': side,
            'x': x,
            'y': y,
            'card': card,
            'hp_current': card['hp'],
            'shell_current': card['shell'],
            'pa_current': card['action_points'],
            'pm_current': card['movement_points'],
            'can_act': True,
            'can_move': True,
            'summoned_turn': state['turn']['number'],
        })
        state['log'].append(f"{side} invocó {card['name']} en ({x}, {y}).")

    elif action == 'move':
        unit = _find_unit(actor, payload.get('unit_id'))
        x, y = payload.get('to_x'), payload.get('to_y')
        if not unit:
            return 'Unidad inválida.'
        if not unit['can_move'] or unit['pm_current'] <= 0:
            return 'La unidad no puede moverse.'
        if not isinstance(x, int) or not isinstance(y, int) or not _in_bounds(x, y, width, height):
            return 'Destino inválido.'

        reachable_cells = _reachable_cells(state, unit)
        distance = reachable_cells.get((x, y))
        if distance is None:
            return 'Movimiento fuera de rango.'

        unit['x'], unit['y'] = x, y
        unit['pm_current'] = max(0, unit['pm_current'] - distance)
        unit['can_move'] = unit['pm_current'] > 0
        state['log'].append(f"{side} movió {unit['card']['name']} a ({x}, {y}).")

    elif action == 'attack':
        attacker = _find_unit(actor, payload.get('attacker_id'))
        target = _find_unit(enemy, payload.get('target_id'))
        if not attacker or not target:
            return 'Ataque inválido.'
        if not _can_attack(attacker, target):
            return 'Objetivo fuera de rango o sin PA.'

        attacker['pa_current'] -= 1
        attacker['can_act'] = attacker['pa_current'] > 0
        attack_power = attacker['card']['action_points'] + 2
        absorbed = min(target['shell_current'], max(0, attack_power - 1))
        target['shell_current'] = max(0, target['shell_current'] - absorbed)
        damage = max(1, attack_power - absorbed)
        target['hp_current'] -= damage
        state['log'].append(
            f"{side} atacó con {attacker['card']['name']} e infligió {damage} de daño."
        )
        if target['hp_current'] <= 0:
            enemy['units'] = [u for u in enemy['units'] if u['id'] != target['id']]
            state['log'].append(f"{target['card']['name']} fue derrotado.")

    elif action == 'end_turn':
        state['turn']['active_side'] = enemy_side
        if enemy_side == 'host':
            state['turn']['number'] += 1
        enemy['max_energy'] = min(MAX_ENERGY, enemy['max_energy'] + 1)
        enemy['energy'] = enemy['max_energy']
        _draw_one(enemy)
        _reset_turn_state(enemy)
        state['log'].append(f"Fin del turno de {side}.")

    else:
        return 'Acción no soportada.'

    if not enemy['units'] and not enemy['hand'] and not enemy['library']:
        state['winner'] = side
    _refresh_counts(state)
    state['log'] = state['log'][-12:]
    return None


def _nearest_enemy(unit, enemy_units):
    if not enemy_units:
        return None
    return min(enemy_units, key=lambda target: _distance(unit, target))


def _best_step_towards(unit, nearest, state):
    best_move = None
    best_distance = _distance(unit, nearest)
    reachable_cells = _reachable_cells(state, unit)

    for (nx, ny), steps in reachable_cells.items():
        candidate_distance = abs(nx - nearest['x']) + abs(ny - nearest['y'])
        if candidate_distance < best_distance or (candidate_distance == best_distance and best_move and steps < best_move[0]):
            best_distance = candidate_distance
            best_move = (steps, nx, ny)
    return best_move


def _ai_turn(state):
    if state['turn']['active_side'] != 'guest' or state['winner']:
        return

    ai = state['guest']
    width = state['board']['width']
    height = state['board']['height']

    if ai['hand']:
        for index, card in enumerate(list(ai['hand'])):
            if ai['energy'] < _summon_cost(card):
                continue
            for x, y in _deployment_cells('guest', width, height):
                if not _occupied(state, x, y):
                    _apply_action(state, 'guest', {'action': 'summon', 'hand_index': index, 'x': x, 'y': y})
                    break
            break

    for unit in list(ai['units']):
        nearest = _nearest_enemy(unit, state['host']['units'])
        if not nearest:
            continue

        while unit['can_act'] and nearest and _can_attack(unit, nearest):
            _apply_action(state, 'guest', {'action': 'attack', 'attacker_id': unit['id'], 'target_id': nearest['id']})
            nearest = _nearest_enemy(unit, state['host']['units'])

        if not nearest or not unit['can_move'] or unit['pm_current'] <= 0:
            continue

        move = _best_step_towards(unit, nearest, state)
        if move:
            _, nx, ny = move
            _apply_action(state, 'guest', {'action': 'move', 'unit_id': unit['id'], 'to_x': nx, 'to_y': ny})
            nearest = _nearest_enemy(unit, state['host']['units'])
            while unit['can_act'] and nearest and _can_attack(unit, nearest):
                _apply_action(state, 'guest', {'action': 'attack', 'attacker_id': unit['id'], 'target_id': nearest['id']})
                nearest = _nearest_enemy(unit, state['host']['units'])

    _apply_action(state, 'guest', {'action': 'end_turn'})


def _match_payload(record):
    state = _state_for_client(record.game_state or {})
    return {
        'room_code': record.room_code,
        'status': record.status,
        'match': {
            'room_code': record.room_code,
            **state,
        },
    }


def _active_match_from_session(request):
    room_code = request.session.get(SESSION_MATCH_KEY)
    if not room_code:
        return None
    try:
        return MatchRecord.objects.get(room_code=room_code, status='active')
    except MatchRecord.DoesNotExist:
        request.session.pop(SESSION_MATCH_KEY, None)
        return None


@require_GET
def index(request):
    _ensure_cards_seeded()
    cards = [_serialize_card(card) for card in MonsterCard.objects.all()]
    return render(request, 'core/index.html', {'cards_seed_json': cards})


@require_GET
def health(request):
    return JsonResponse({'ok': True})


@require_GET
def cards_catalog(request):
    _ensure_cards_seeded()
    cards = [_serialize_card(card) for card in MonsterCard.objects.all()]
    return JsonResponse({'ok': True, 'cards': cards})


@require_GET
def get_active_match(request):
    record = _active_match_from_session(request)
    if not record:
        return JsonResponse({'ok': True, 'room_code': None, 'match': None})
    return JsonResponse({'ok': True, **_match_payload(record)})


@require_http_methods(['POST'])
def create_match_vs_ai(request):
    _ensure_cards_seeded()
    cards = list(MonsterCard.objects.all())
    ai_user = _get_or_create_system_user(AI_USERNAME)
    solo_system_user = _get_or_create_system_user(SOLO_SYSTEM_USERNAME)

    record = _active_match_from_session(request)
    if record:
        record.game_state = _build_new_match_state(cards)
        record.status = 'active'
        record.guest = ai_user
        record.winner = None
        record.save(update_fields=['game_state', 'status', 'guest', 'winner', 'updated_at'])
    else:
        record = MatchRecord.objects.create(
            host=solo_system_user,
            guest=ai_user,
            status='active',
            game_state=_build_new_match_state(cards),
        )

    request.session[SESSION_MATCH_KEY] = record.room_code
    request.session.modified = True
    return JsonResponse({'ok': True, **_match_payload(record)})


@require_GET
def get_match(request, room_code):
    session_room = request.session.get(SESSION_MATCH_KEY)
    if not session_room or session_room != room_code:
        return _json_error('Partida no disponible para esta sesión.', status=404)
    try:
        record = MatchRecord.objects.get(room_code=room_code, status='active')
    except MatchRecord.DoesNotExist:
        return _json_error('La partida no existe o ya no está activa.', status=404)
    return JsonResponse({'ok': True, **_match_payload(record)})


@require_http_methods(['POST'])
def match_action(request, room_code):
    session_room = request.session.get(SESSION_MATCH_KEY)
    if not session_room or session_room != room_code:
        return _json_error('Partida no disponible para esta sesión.', status=404)

    try:
        record = MatchRecord.objects.get(room_code=room_code, status='active')
    except MatchRecord.DoesNotExist:
        return _json_error('La partida no existe o ya no está activa.', status=404)

    state = record.game_state or {}
    error = _apply_action(state, 'host', _payload(request))
    if error:
        return _json_error(error)

    _ai_turn(state)
    if state.get('winner'):
        record.status = 'finished'
    record.game_state = state
    record.save(update_fields=['game_state', 'status', 'updated_at'])
    return JsonResponse({'ok': True, **_match_payload(record)})
