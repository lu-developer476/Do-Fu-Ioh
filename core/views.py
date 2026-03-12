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
BOARD_WIDTH = 6
BOARD_HEIGHT = 4


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
        'units': [],
    }


def _create_initial_state(host, guest=None):
    host_deck = _get_active_deck(host)
    guest_deck = _get_active_deck(guest) if guest else None
    return {
        'turn': 'host',
        'turn_number': 1,
        'winner': None,
        'board': {'width': BOARD_WIDTH, 'height': BOARD_HEIGHT},
        'log': ['Partida creada: tablero táctico listo.'],
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


def _is_cell_free(state, x, y):
    for side in ['host', 'guest']:
        player = state.get(side)
        if not player:
            continue
        for unit in player['units']:
            if unit['x'] == x and unit['y'] == y and unit['current_hp'] > 0:
                return False
    return True


def _summon_rows_for_side(side):
    return {0, 1} if side == 'host' else {BOARD_HEIGHT - 1, BOARD_HEIGHT - 2}


def _combat_range(card):
    base = 1 if card['stage'] == 'base' else 2
    return min(4, base + card['action_points'] // 2)


def _combat_damage(card):
    return max(1, card['action_points'] + (card['level_max'] - card['level_min'] + 1) // 2)


def _find_unit(player_state, unit_id):
    for unit in player_state['units']:
        if unit['id'] == unit_id:
            return unit
    return None


def _public_state(state, viewer_side):
    public_state = deepcopy(state)
    hidden = 'guest' if viewer_side == 'host' else 'host'
    if public_state.get(hidden):
        public_state[hidden]['library_count'] = len(public_state[hidden]['library'])
        public_state[hidden]['hand_count'] = len(public_state[hidden]['hand'])
        public_state[hidden].pop('library', None)
        public_state[hidden].pop('hand', None)
    if public_state.get(viewer_side):
        public_state[viewer_side]['library_count'] = len(public_state[viewer_side]['library'])
    return public_state


@require_http_methods(['POST'])
@csrf_exempt
def create_match(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    _ensure_default_deck(request.user)
    match = MatchRecord.objects.create(host=request.user, game_state=_create_initial_state(request.user))
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
    match.game_state = _create_initial_state(match.host, request.user)
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
    for unit in player['units']:
        if unit['current_hp'] <= 0:
            continue
        unit['ap_left'] = unit['card']['action_points']
        unit['pm_left'] = unit['card']['movement_points']


def _require_turn(state, side):
    return state['turn'] == side and not state.get('winner')


@require_http_methods(['POST'])
@csrf_exempt
def match_action(request, room_code):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'No autenticado'}, status=401)
    match = get_object_or_404(MatchRecord, room_code=room_code)
    side = _match_side(match, request.user)
    if not side:
        return JsonResponse({'status': 'error', 'message': 'No perteneces a esta sala'}, status=403)

    state = deepcopy(match.game_state)
    if not state.get('guest'):
        return JsonResponse({'status': 'error', 'message': 'Esperando rival'}, status=409)
    if not _require_turn(state, side):
        return JsonResponse({'status': 'error', 'message': 'No es tu turno'}, status=409)

    data = _payload(request)
    action = data.get('action')
    player = state[side]
    enemy = state[_enemy_side(side)]

    if action == 'summon':
        hand_index = int(data.get('hand_index', -1))
        x = int(data.get('x', -1))
        y = int(data.get('y', -1))
        if hand_index < 0 or hand_index >= len(player['hand']):
            return JsonResponse({'status': 'error', 'message': 'Carta inválida'}, status=400)
        if not _is_inside_board(x, y):
            return JsonResponse({'status': 'error', 'message': 'Casilla fuera del tablero'}, status=400)
        if y not in _summon_rows_for_side(side):
            return JsonResponse({'status': 'error', 'message': 'Solo puedes invocar en tu zona de despliegue'}, status=400)
        if not _is_cell_free(state, x, y):
            return JsonResponse({'status': 'error', 'message': 'Casilla ocupada'}, status=400)
        if player['energy'] < 1:
            return JsonResponse({'status': 'error', 'message': 'No te alcanza la energía'}, status=400)

        card = player['hand'].pop(hand_index)
        player['energy'] -= 1
        player['units'].append({
            'id': f"u-{card['slug']}-{random.randint(1000, 9999)}",
            'owner': side,
            'x': x,
            'y': y,
            'card': card,
            'current_hp': card['hp'],
            'current_shell': card['shell'],
            'ap_left': 0,
            'pm_left': 0,
            'summoned_on_turn': state['turn_number'],
        })
        state['log'].append(f"{player['username']} invocó {card['name']} en ({x},{y}).")

    elif action == 'move':
        unit_id = data.get('unit_id')
        to_x = int(data.get('to_x', -1))
        to_y = int(data.get('to_y', -1))
        unit = _find_unit(player, unit_id)
        if not unit:
            return JsonResponse({'status': 'error', 'message': 'Unidad inválida'}, status=400)
        if not _is_inside_board(to_x, to_y):
            return JsonResponse({'status': 'error', 'message': 'Destino fuera del tablero'}, status=400)
        if not _is_cell_free(state, to_x, to_y):
            return JsonResponse({'status': 'error', 'message': 'Casilla ocupada'}, status=400)
        distance = _manhattan(unit['x'], unit['y'], to_x, to_y)
        if distance <= 0:
            return JsonResponse({'status': 'error', 'message': 'Movimiento nulo'}, status=400)
        if unit['pm_left'] < distance:
            return JsonResponse({'status': 'error', 'message': 'No tienes PM suficientes'}, status=400)
        unit['x'] = to_x
        unit['y'] = to_y
        unit['pm_left'] -= distance
        state['log'].append(f"{unit['card']['name']} se movió a ({to_x},{to_y}).")

    elif action == 'attack':
        attacker_id = data.get('attacker_id')
        target_id = data.get('target_id')
        attacker = _find_unit(player, attacker_id)
        target = _find_unit(enemy, target_id)
        if not attacker or not target:
            return JsonResponse({'status': 'error', 'message': 'Ataque inválido'}, status=400)
        if attacker['ap_left'] < 1:
            return JsonResponse({'status': 'error', 'message': 'No tienes PA suficientes'}, status=400)
        if attacker['summoned_on_turn'] == state['turn_number']:
            return JsonResponse({'status': 'error', 'message': 'La unidad no puede atacar el turno en que fue invocada'}, status=400)

        distance = _manhattan(attacker['x'], attacker['y'], target['x'], target['y'])
        if distance > _combat_range(attacker['card']):
            return JsonResponse({'status': 'error', 'message': 'Objetivo fuera de alcance'}, status=400)

        damage = _combat_damage(attacker['card'])
        attacker['ap_left'] -= 1

        remaining = damage
        if target['current_shell'] > 0:
            absorbed = min(target['current_shell'], remaining)
            target['current_shell'] -= absorbed
            remaining -= absorbed
        if remaining > 0:
            target['current_hp'] -= remaining

        if target['current_hp'] <= 0:
            enemy['graveyard'].append(target['card'])
            enemy['units'] = [u for u in enemy['units'] if u['id'] != target['id']]
            state['log'].append(f"{attacker['card']['name']} derrotó a {target['card']['name']}.")
        else:
            state['log'].append(f"{attacker['card']['name']} golpeó a {target['card']['name']} por {damage}.")

    elif action == 'direct_attack':
        attacker_id = data.get('attacker_id')
        attacker = _find_unit(player, attacker_id)
        if not attacker:
            return JsonResponse({'status': 'error', 'message': 'Unidad inválida'}, status=400)
        if attacker['ap_left'] < 1:
            return JsonResponse({'status': 'error', 'message': 'No tienes PA suficientes'}, status=400)
        if attacker['summoned_on_turn'] == state['turn_number']:
            return JsonResponse({'status': 'error', 'message': 'La unidad no puede atacar el turno en que fue invocada'}, status=400)

        damage = max(1, _combat_damage(attacker['card']) - 1)
        attacker['ap_left'] -= 1
        enemy['life'] -= damage
        state['log'].append(f"{attacker['card']['name']} hizo ataque directo por {damage}.")
        _check_winner(match, state)

    elif action == 'end_turn':
        next_side = _enemy_side(side)
        state['turn'] = next_side
        state['turn_number'] += 1
        _start_turn(state, next_side)
        state['log'].append(f"{player['username']} terminó su turno.")

    else:
        return JsonResponse({'status': 'error', 'message': 'Acción desconocida'}, status=400)

    match.game_state = state
    match.save(update_fields=['game_state', 'status', 'winner', 'updated_at'])
    return JsonResponse({'status': 'ok', 'room_code': room_code, 'match': _public_state(state, side)})
