import json
import random
import secrets
import unicodedata
from collections import deque
from pathlib import Path

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .models import MatchRecord, MonsterCard
from .system_users import get_single_player_system_users

BOARD_WIDTH = 11
BOARD_HEIGHT = 11
HAND_SIZE = 5
DECK_SIZE = 12
MAX_ENERGY = 10
AI_DIFFICULTIES = {"normal", "extremo"}
SESSION_MATCH_KEY = "active_ai_match_room_code"
CARDS_DATA_PATH = Path(settings.BASE_DIR) / "data" / "cards.json"
SUMMON_COST_BY_STAGE = {
    "base": 1,
    "fusion": 3,
    "evolution": 5,
}
STAGE_RANK = {"base": 0, "fusion": 1, "evolution": 2}
SUPPORTED_ACTIONS = {"summon", "move", "attack", "end_turn"}
ACTION_FIELD_TYPES = {
    "summon": {"hand_index": int, "x": int, "y": int},
    "move": {"unit_id": str, "to_x": int, "to_y": int},
    "attack": {"attacker_id": str, "target_id": str},
    "end_turn": {},
}


# Payload / response helpers

def _slugify(value: str) -> str:
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    return "-".join(part for part in value.split("-") if part)[:140]


def _payload(request):
    try:
        return json.loads((request.body or b"{}").decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


def _state_error(message, status=500):
    return _json_error(f"Estado de partida inválido: {message}", status=status)


# Card serialization / loading

def _resolve_card_image(image):
    raw = (image or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://", "/")):
        return raw
    cleaned = raw[7:] if raw.startswith("public/") else raw
    return f"/static/{cleaned}"


def _summon_cost(card_like):
    stage = card_like.get("stage", "base")
    return SUMMON_COST_BY_STAGE.get(stage, 1)


def _serialize_card(card):
    return {
        "id": card.id,
        "name": card.name,
        "slug": card.slug,
        "family": card.family,
        "stage": card.stage,
        "level_min": card.level_min,
        "level_max": card.level_max,
        "hp": card.hp,
        "shell": card.shell,
        "action_points": card.action_points,
        "movement_points": card.movement_points,
        "description": card.description,
        "image": _resolve_card_image(card.image),
        "summon_cost": _summon_cost({"stage": card.stage}),
    }


def _serialized_cards_queryset():
    return [_serialize_card(card) for card in MonsterCard.objects.all()]


def _ensure_cards_seeded():
    if not CARDS_DATA_PATH.exists():
        return

    try:
        if MonsterCard.objects.exists():
            return
    except (ProgrammingError, OperationalError):
        return

    cards = json.loads(CARDS_DATA_PATH.read_text(encoding="utf-8"))
    for item in cards:
        MonsterCard.objects.update_or_create(
            slug=_slugify(item["name"]),
            defaults={
                "family": item["family"],
                "name": item["name"],
                "stage": item["stage"],
                "level_min": item["level_min"],
                "level_max": item["level_max"],
                "hp": item["hp"],
                "shell": item["shell"],
                "action_points": item["action_points"],
                "movement_points": item["movement_points"],
                "description": item.get("description", ""),
                "image": item.get("image", ""),
            },
        )


# Match building

def _player_state(side, deck_cards):
    random.shuffle(deck_cards)
    hand = deck_cards[:HAND_SIZE]
    library = deck_cards[HAND_SIZE:]
    return {
        "side": side,
        "energy": 1,
        "max_energy": 1,
        "hand": hand,
        "library": library,
        "library_count": len(library),
        "hand_count": len(hand),
        "units": [],
        "summons_this_turn": 0,
    }


def _build_deck(serialized_cards):
    if not serialized_cards:
        return []
    base_cards = [card for card in serialized_cards if card["stage"] == "base"]
    non_base_cards = [card for card in serialized_cards if card["stage"] != "base"]
    guaranteed = random.choices(
        base_cards or serialized_cards, k=min(HAND_SIZE, DECK_SIZE)
    )
    remaining_pool = non_base_cards or serialized_cards
    weights = [2 if card["stage"] == "fusion" else 1 for card in remaining_pool]
    remaining = random.choices(
        remaining_pool, weights=weights, k=max(0, DECK_SIZE - len(guaranteed))
    )
    deck = guaranteed + remaining
    random.shuffle(deck)
    return deck


def _normalize_ai_difficulty(value):
    difficulty = (value or "normal").strip().lower()
    return difficulty if difficulty in AI_DIFFICULTIES else "normal"


def _empty_match_state(difficulty):
    return {
        "mode": "vs_ai",
        "ai_difficulty": difficulty,
        "board": {"width": BOARD_WIDTH, "height": BOARD_HEIGHT},
        "turn": {"number": 1, "active_side": "host"},
        "host": _player_state("host", []),
        "guest": _player_state("guest", []),
        "winner": None,
        "log": ["No hay cartas cargadas en la base de datos."],
    }


def _build_new_match_state(cards, difficulty="normal"):
    difficulty = _normalize_ai_difficulty(difficulty)
    serialized = [_serialize_card(card) for card in cards]
    if not serialized:
        return _empty_match_state(difficulty)

    return {
        "mode": "vs_ai",
        "ai_difficulty": difficulty,
        "board": {"width": BOARD_WIDTH, "height": BOARD_HEIGHT},
        "turn": {"number": 1, "active_side": "host"},
        "host": _player_state("host", _build_deck(serialized)),
        "guest": _player_state("guest", _build_deck(serialized)),
        "winner": None,
        "log": ["Partida iniciada: jugador vs IA."],
    }




# Validation helpers

def _draw_one(player):
    if not player["library"]:
        return
    player["hand"].append(player["library"].pop(0))
    player["library_count"] = len(player["library"])
    player["hand_count"] = len(player["hand"])


def _is_non_negative_int(value):
    return isinstance(value, int) and value >= 0


def _validate_card_payload(card, context):
    if not isinstance(card, dict):
        return f"{context} debe ser un objeto."

    for field in ("name", "stage"):
        if not isinstance(card.get(field), str) or not card[field].strip():
            return f"{context}.{field} es obligatorio."

    for field in ("hp", "shell", "action_points", "movement_points"):
        if not _is_non_negative_int(card.get(field)):
            return f"{context}.{field} debe ser un entero mayor o igual a 0."

    return None


def _validate_unit_payload(unit, side, index, width, height):
    context = f"{side}.units[{index}]"
    if not isinstance(unit, dict):
        return f"{context} debe ser un objeto."

    if not isinstance(unit.get("id"), str) or not unit["id"].strip():
        return f"{context}.id es obligatorio."
    if unit.get("owner") != side:
        return f"{context}.owner debe ser '{side}'."
    if not _is_non_negative_int(unit.get("x")) or not _is_non_negative_int(unit.get("y")):
        return f"{context} debe incluir coordenadas válidas."
    if not _in_bounds(unit["x"], unit["y"], width, height):
        return f"{context} está fuera del tablero."

    card_error = _validate_card_payload(unit.get("card"), f"{context}.card")
    if card_error:
        return card_error

    for field in ("hp_current", "shell_current", "pa_current", "pm_current", "summoned_turn"):
        if not _is_non_negative_int(unit.get(field)):
            return f"{context}.{field} debe ser un entero mayor o igual a 0."

    for field in ("can_act", "can_move"):
        if not isinstance(unit.get(field), bool):
            return f"{context}.{field} debe ser booleano."

    return None


def _validate_player_state(player, side, width, height):
    if not isinstance(player, dict):
        return f"{side} debe ser un objeto."
    if player.get("side") != side:
        return f"{side}.side debe ser '{side}'."

    for field in ("energy", "max_energy", "library_count", "hand_count", "summons_this_turn"):
        if not _is_non_negative_int(player.get(field)):
            return f"{side}.{field} debe ser un entero mayor o igual a 0."

    for field in ("hand", "library", "units"):
        if not isinstance(player.get(field), list):
            return f"{side}.{field} debe ser una lista."

    for index, card in enumerate(player["hand"]):
        card_error = _validate_card_payload(card, f"{side}.hand[{index}]")
        if card_error:
            return card_error

    for index, card in enumerate(player["library"]):
        card_error = _validate_card_payload(card, f"{side}.library[{index}]")
        if card_error:
            return card_error

    for index, unit in enumerate(player["units"]):
        unit_error = _validate_unit_payload(unit, side, index, width, height)
        if unit_error:
            return unit_error

    if player["energy"] > player["max_energy"]:
        return f"{side}.energy no puede superar max_energy."

    return None


def _validate_match_state(state):
    if not isinstance(state, dict):
        return "la raíz debe ser un objeto JSON."

    board = state.get("board")
    if not isinstance(board, dict):
        return "board debe ser un objeto."
    width = board.get("width")
    height = board.get("height")
    if not _is_non_negative_int(width) or width <= 0:
        return "board.width debe ser un entero positivo."
    if not _is_non_negative_int(height) or height <= 0:
        return "board.height debe ser un entero positivo."

    turn = state.get("turn")
    if not isinstance(turn, dict):
        return "turn debe ser un objeto."
    if not _is_non_negative_int(turn.get("number")) or turn["number"] <= 0:
        return "turn.number debe ser un entero positivo."
    if turn.get("active_side") not in {"host", "guest"}:
        return "turn.active_side debe ser 'host' o 'guest'."

    for side in ("host", "guest"):
        player_error = _validate_player_state(state.get(side), side, width, height)
        if player_error:
            return player_error

    if state.get("winner") not in {None, "host", "guest"}:
        return "winner debe ser null, 'host' o 'guest'."

    if not isinstance(state.get("log"), list):
        return "log debe ser una lista."
    if any(not isinstance(item, str) for item in state["log"]):
        return "log sólo puede contener textos."

    return None


def _validate_action_payload(payload):
    if not isinstance(payload, dict):
        return "El cuerpo de la acción debe ser un objeto JSON."

    action = payload.get("action")
    if action not in SUPPORTED_ACTIONS:
        return "Acción no soportada."

    for field, expected_type in ACTION_FIELD_TYPES[action].items():
        value = payload.get(field)
        if expected_type is int and not isinstance(value, int):
            return f"El campo '{field}' debe ser un entero."
        if expected_type is str and (not isinstance(value, str) or not value.strip()):
            return f"El campo '{field}' debe ser un texto no vacío."

    return None


# Board helpers / derived state

def _in_bounds(x, y, width, height):
    return 0 <= x < width and 0 <= y < height


def _deployment_cells(side, width, height):
    center = width // 2
    if side == "host":
        return {(center, 0), (center - 1, 1), (center, 1), (center + 1, 1), (center, 2)}
    return {
        (center, height - 1),
        (center - 1, height - 2),
        (center, height - 2),
        (center + 1, height - 2),
        (center, height - 3),
    }


def _find_unit(player, unit_id):
    for unit in player["units"]:
        if unit["id"] == unit_id:
            return unit
    return None


def _occupied(state, x, y):
    return any(
        unit["x"] == x and unit["y"] == y
        for unit in state["host"]["units"] + state["guest"]["units"]
    )


def _occupied_positions(state, ignore_unit_id=None):
    positions = set()
    for unit in state["host"]["units"] + state["guest"]["units"]:
        if ignore_unit_id and unit["id"] == ignore_unit_id:
            continue
        positions.add((unit["x"], unit["y"]))
    return positions


def _reachable_cells(state, unit):
    max_steps = unit.get("pm_current", 0)
    if not unit.get("can_move") or max_steps <= 0:
        return {}

    width = state["board"]["width"]
    height = state["board"]["height"]
    blocked = _occupied_positions(state, ignore_unit_id=unit["id"])
    origin = (unit["x"], unit["y"])
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
            previous = distances.get((nx, ny))
            if next_distance <= max_steps and (previous is None or next_distance < previous):
                distances[(nx, ny)] = next_distance
                queue.append((nx, ny))

    distances.pop(origin, None)
    return distances


def _serialize_reachable_cells(state, unit):
    return [
        {"x": x, "y": y, "distance": distance}
        for (x, y), distance in sorted(
            _reachable_cells(state, unit).items(),
            key=lambda item: (item[1], item[0][1], item[0][0]),
        )
    ]


def _attack_range(unit):
    base_range = 1 if unit["card"]["stage"] == "base" else 2
    return min(5, base_range + unit["card"]["action_points"] // 2)


def _attackable_unit_ids(state, attacker, enemy_side=None):
    if attacker["pa_current"] <= 0 or not attacker["can_act"]:
        return []

    side = enemy_side or ("guest" if attacker["owner"] == "host" else "host")
    attack_range = _attack_range(attacker)
    attackable = []
    for target in state.get(side, {}).get("units", []):
        distance = abs(attacker["x"] - target["x"]) + abs(attacker["y"] - target["y"])
        if distance <= attack_range:
            attackable.append(target["id"])
    return sorted(attackable)


def _state_for_client(state):
    payload = json.loads(json.dumps(state))
    for side in ("host", "guest"):
        enemy_side = "guest" if side == "host" else "host"
        for unit in payload.get(side, {}).get("units", []):
            unit["reachable_cells"] = _serialize_reachable_cells(payload, unit)
            unit["attack_range"] = _attack_range(unit)
            unit["attackable_unit_ids"] = _attackable_unit_ids(
                payload, unit, enemy_side=enemy_side
            )
    return payload


def _can_attack(state, attacker, target):
    return target["id"] in _attackable_unit_ids(state, attacker, enemy_side=target["owner"])


def _distance(a, b):
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])


def _threatened_by_enemy_count(position, enemy_units):
    x, y = position
    threatened = 0
    for enemy in enemy_units:
        if abs(enemy["x"] - x) + abs(enemy["y"] - y) <= _attack_range(enemy):
            threatened += 1
    return threatened


def _enemy_pressure(position, enemy_units):
    x, y = position
    if not enemy_units:
        return 0
    return min(abs(enemy["x"] - x) + abs(enemy["y"] - y) for enemy in enemy_units)


# Match state mutations

def _refresh_counts(state):
    for side in ("host", "guest"):
        state[side]["library_count"] = len(state[side]["library"])
        state[side]["hand_count"] = len(state[side]["hand"])


def _player_has_remaining_resources(player):
    return bool(player["units"] or player["hand"] or player["library"])


def _update_winner_for_current_mode(state, acting_side):
    host_still_in_game = _player_has_remaining_resources(state["host"])
    guest_still_in_game = _player_has_remaining_resources(state["guest"])

    if host_still_in_game and guest_still_in_game:
        return
    if host_still_in_game:
        state["winner"] = "host"
        return
    if guest_still_in_game:
        state["winner"] = "guest"
        return
    state["winner"] = acting_side


def _reset_turn_state(player):
    player["summons_this_turn"] = 0
    for unit in player["units"]:
        unit["pa_current"] = unit["card"]["action_points"]
        unit["pm_current"] = unit["card"]["movement_points"]
        unit["can_act"] = True
        unit["can_move"] = True


def _append_log(state, message):
    state["log"].append(message)
    state["log"] = state["log"][-12:]


def _build_unit_from_card(state, side, card, x, y):
    return {
        "id": secrets.token_hex(6),
        "owner": side,
        "x": x,
        "y": y,
        "card": card,
        "hp_current": card["hp"],
        "shell_current": card["shell"],
        "pa_current": card["action_points"],
        "pm_current": card["movement_points"],
        "can_act": True,
        "can_move": True,
        "summoned_turn": state["turn"]["number"],
    }


def _apply_summon_action(state, side, actor, payload):
    width = state["board"]["width"]
    height = state["board"]["height"]
    hand_index = payload.get("hand_index")
    x, y = payload.get("x"), payload.get("y")

    if not isinstance(hand_index, int) or hand_index < 0 or hand_index >= len(actor["hand"]):
        return "Carta inválida."
    if not isinstance(x, int) or not isinstance(y, int) or not _in_bounds(x, y, width, height):
        return "Casilla inválida."
    if (x, y) not in _deployment_cells(side, width, height):
        return "Sólo podés invocar en tu zona azul."
    if _occupied(state, x, y):
        return "Esa casilla ya está ocupada."
    if actor["summons_this_turn"] >= 1:
        return "Ya invocaste este turno."

    card = actor["hand"].pop(hand_index)
    cost = _summon_cost(card)
    if actor["energy"] < cost:
        actor["hand"].insert(hand_index, card)
        return "No alcanza la energía para invocar."

    actor["energy"] -= cost
    actor["summons_this_turn"] += 1
    actor["units"].append(_build_unit_from_card(state, side, card, x, y))
    _append_log(state, f"{side} invocó {card['name']} en ({x}, {y}).")
    return None


def _apply_move_action(state, side, actor, payload):
    width = state["board"]["width"]
    height = state["board"]["height"]
    unit = _find_unit(actor, payload.get("unit_id"))
    x, y = payload.get("to_x"), payload.get("to_y")

    if not unit:
        return "Unidad inválida."
    if not unit["can_move"] or unit["pm_current"] <= 0:
        return "La unidad no puede moverse."
    if not isinstance(x, int) or not isinstance(y, int) or not _in_bounds(x, y, width, height):
        return "Destino inválido."

    distance = _reachable_cells(state, unit).get((x, y))
    if distance is None:
        return "Movimiento fuera de rango."

    unit["x"], unit["y"] = x, y
    unit["pm_current"] = max(0, unit["pm_current"] - distance)
    unit["can_move"] = unit["pm_current"] > 0
    _append_log(state, f"{side} movió {unit['card']['name']} a ({x}, {y}).")
    return None


def _apply_attack_action(state, side, actor, enemy, payload):
    attacker = _find_unit(actor, payload.get("attacker_id"))
    target = _find_unit(enemy, payload.get("target_id"))
    if not attacker or not target:
        return "Ataque inválido."
    if not _can_attack(state, attacker, target):
        return "Objetivo fuera de rango o sin PA."

    attacker["pa_current"] -= 1
    attacker["can_act"] = attacker["pa_current"] > 0
    attack_power = attacker["card"]["action_points"] + 2
    absorbed = min(target["shell_current"], max(0, attack_power - 1))
    target["shell_current"] = max(0, target["shell_current"] - absorbed)
    damage = max(1, attack_power - absorbed)
    target["hp_current"] -= damage
    _append_log(
        state,
        f"{side} atacó con {attacker['card']['name']} e infligió {damage} de daño.",
    )
    if target["hp_current"] <= 0:
        enemy["units"] = [unit for unit in enemy["units"] if unit["id"] != target["id"]]
        _append_log(state, f"{target['card']['name']} fue derrotado.")
    return None


def _apply_end_turn_action(state, side, enemy_side, enemy):
    state["turn"]["active_side"] = enemy_side
    if enemy_side == "host":
        state["turn"]["number"] += 1
    enemy["max_energy"] = min(MAX_ENERGY, enemy["max_energy"] + 1)
    enemy["energy"] = enemy["max_energy"]
    _draw_one(enemy)
    _reset_turn_state(enemy)
    _append_log(state, f"Fin del turno de {side}.")
    return None


def _apply_action(state, side, payload):
    if state["winner"]:
        return "La partida ya terminó."
    if state["turn"]["active_side"] != side:
        return "No es tu turno."

    actor = state[side]
    enemy_side = "guest" if side == "host" else "host"
    enemy = state[enemy_side]
    action = payload.get("action")

    handlers = {
        "summon": lambda: _apply_summon_action(state, side, actor, payload),
        "move": lambda: _apply_move_action(state, side, actor, payload),
        "attack": lambda: _apply_attack_action(state, side, actor, enemy, payload),
        "end_turn": lambda: _apply_end_turn_action(state, side, enemy_side, enemy),
    }
    handler = handlers.get(action)
    if handler is None:
        return "Acción no soportada."

    error = handler()
    if error:
        return error

    _update_winner_for_current_mode(state, side)
    _refresh_counts(state)
    return None


# AI helpers

def _select_attack_target(state, unit, difficulty):
    attackable_ids = _attackable_unit_ids(state, unit, enemy_side="host")
    if not attackable_ids:
        return None

    host_units = {enemy["id"]: enemy for enemy in state["host"]["units"]}
    attack_power = unit["card"]["action_points"] + 2

    def score(target):
        shell_after_block = max(0, attack_power - target["shell_current"])
        potential_damage = max(1, shell_after_block)
        lethal = target["hp_current"] <= potential_damage
        base_score = [1 if lethal else 0]
        if difficulty == "extremo":
            base_score.extend(
                [
                    potential_damage,
                    target["card"]["action_points"],
                    -target["hp_current"],
                    -_distance(unit, target),
                ]
            )
        else:
            base_score.extend(
                [potential_damage, -_distance(unit, target), -target["hp_current"]]
            )
        return tuple(base_score)

    return max((host_units[target_id] for target_id in attackable_ids), key=score)


def _nearest_enemy(unit, enemy_units, difficulty="normal"):
    if not enemy_units:
        return None

    def score(target):
        base = (_distance(unit, target), -target["card"]["action_points"], target["hp_current"])
        if difficulty == "extremo":
            return base + (-target["card"]["movement_points"],)
        return base

    return min(enemy_units, key=score)


def _best_summon_action(state, difficulty):
    ai = state["guest"]
    affordable_cards = [
        (index, card)
        for index, card in enumerate(ai["hand"])
        if _summon_cost(card) <= ai["energy"]
    ]
    if not affordable_cards or ai["summons_this_turn"] >= 1:
        return None

    open_cells = [
        cell
        for cell in _deployment_cells("guest", state["board"]["width"], state["board"]["height"])
        if not _occupied(state, *cell)
    ]
    if not open_cells:
        return None

    enemy_units = state["host"]["units"]

    def card_priority(item):
        _, card = item
        priority = (
            STAGE_RANK.get(card["stage"], 0),
            card["action_points"],
            card["hp"],
            card["movement_points"],
        )
        if difficulty == "extremo":
            return (
                STAGE_RANK.get(card["stage"], 0),
                card["action_points"],
                card["movement_points"],
                card["hp"],
                -_summon_cost(card),
            )
        return priority

    def cell_priority(cell):
        x, y = cell
        pressure = _enemy_pressure(cell, enemy_units)
        threatened = _threatened_by_enemy_count(cell, enemy_units)
        advance = -y
        center_bias = -abs(x - state["board"]["width"] // 2)
        if difficulty == "extremo":
            return (advance, -threatened, -pressure, center_bias)
        return (advance, -pressure, -threatened, center_bias)

    hand_index, _ = max(affordable_cards, key=card_priority)
    x, y = max(open_cells, key=cell_priority)
    return {"action": "summon", "hand_index": hand_index, "x": x, "y": y}


def _best_step_towards(unit, target, state, difficulty):
    reachable_cells = _reachable_cells(state, unit)
    if not reachable_cells:
        return None

    current_distance = _distance(unit, target)
    enemy_units = state["host"]["units"]
    candidates = []
    for (nx, ny), steps in reachable_cells.items():
        candidate = {"x": nx, "y": ny}
        distance_to_target = _distance(candidate, target)
        attack_options = sum(
            1
            for enemy in enemy_units
            if abs(nx - enemy["x"]) + abs(ny - enemy["y"]) <= _attack_range(unit)
        )
        threatened = _threatened_by_enemy_count((nx, ny), enemy_units)
        forward_progress = unit["y"] - ny
        score = [1 if distance_to_target < current_distance else 0]
        if difficulty == "extremo":
            score.extend(
                [
                    attack_options,
                    -distance_to_target,
                    forward_progress,
                    -threatened,
                    -steps,
                    -abs(nx - target["x"]),
                ]
            )
        else:
            score.extend(
                [-distance_to_target, attack_options, forward_progress, -steps, -threatened]
            )
        candidates.append((tuple(score), steps, nx, ny))

    best = max(candidates, key=lambda item: item[0])
    if best[0][0] <= 0 and _enemy_pressure((best[2], best[3]), enemy_units) >= _enemy_pressure(
        (unit["x"], unit["y"]), enemy_units
    ):
        return None
    _, steps, nx, ny = best
    return steps, nx, ny


def _ai_attack_phase(state, unit, difficulty):
    while True:
        target = _select_attack_target(state, unit, difficulty)
        if not target or not unit["can_act"]:
            break
        _apply_action(
            state,
            "guest",
            {"action": "attack", "attacker_id": unit["id"], "target_id": target["id"]},
        )
        if state.get("winner"):
            return True
    return False


def _ai_move_phase(state, unit, difficulty):
    if not unit["can_move"] or unit["pm_current"] <= 0 or not state["host"]["units"]:
        return

    nearest = _nearest_enemy(unit, state["host"]["units"], difficulty=difficulty)
    move = _best_step_towards(unit, nearest, state, difficulty)
    if move:
        _, nx, ny = move
        _apply_action(
            state,
            "guest",
            {"action": "move", "unit_id": unit["id"], "to_x": nx, "to_y": ny},
        )


def _ai_turn(state):
    if state["turn"]["active_side"] != "guest" or state["winner"]:
        return

    difficulty = _normalize_ai_difficulty(state.get("ai_difficulty"))
    summon_action = _best_summon_action(state, difficulty)
    if summon_action:
        _apply_action(state, "guest", summon_action)

    for unit in list(state["guest"]["units"]):
        if _ai_attack_phase(state, unit, difficulty):
            break
        if state.get("winner"):
            break
        _ai_move_phase(state, unit, difficulty)
        if _ai_attack_phase(state, unit, difficulty):
            break
        if state.get("winner"):
            break

    if not state["winner"]:
        _apply_action(state, "guest", {"action": "end_turn"})


# Match persistence / responses

def _match_payload(record):
    state = _state_for_client(record.game_state or {})
    return {
        "room_code": record.room_code,
        "status": record.status,
        "match": {"room_code": record.room_code, **state},
    }


def _active_match_from_session(request):
    room_code = request.session.get(SESSION_MATCH_KEY)
    if not room_code:
        return None
    try:
        return MatchRecord.objects.get(room_code=room_code, status="active")
    except MatchRecord.DoesNotExist:
        request.session.pop(SESSION_MATCH_KEY, None)
        return None


def _get_session_match_or_error(request, room_code):
    session_room = request.session.get(SESSION_MATCH_KEY)
    if not session_room or session_room != room_code:
        return None, _json_error("Partida no disponible para esta sesión.", status=404)

    try:
        return MatchRecord.objects.get(room_code=room_code, status="active"), None
    except MatchRecord.DoesNotExist:
        return None, _json_error("La partida no existe o ya no está activa.", status=404)


def _validated_record_state(record):
    state = record.game_state or {}
    state_error = _validate_match_state(state)
    if state_error:
        return None, _state_error(state_error)
    return state, None


@require_GET
@ensure_csrf_cookie
def index(request):
    _ensure_cards_seeded()
    return render(request, "core/index.html", {"cards_seed_json": _serialized_cards_queryset()})


@require_GET
def health(request):
    return JsonResponse({"ok": True})


@require_GET
def cards_catalog(request):
    _ensure_cards_seeded()
    return JsonResponse({"ok": True, "cards": _serialized_cards_queryset()})


@require_GET
def get_active_match(request):
    record = _active_match_from_session(request)
    if not record:
        return JsonResponse({"ok": True, "room_code": None, "match": None})
    _, error_response = _validated_record_state(record)
    if error_response:
        return error_response
    return JsonResponse({"ok": True, **_match_payload(record)})


@require_http_methods(["POST"])
def create_match_vs_ai(request):
    _ensure_cards_seeded()
    payload = _payload(request)
    difficulty = _normalize_ai_difficulty(payload.get("difficulty"))
    cards = list(MonsterCard.objects.all())
    solo_system_user, ai_user = get_single_player_system_users()

    record = _active_match_from_session(request)
    if record:
        record.game_state = _build_new_match_state(cards, difficulty=difficulty)
        record.status = "active"
        record.guest = ai_user
        record.winner = None
        record.save(update_fields=["game_state", "status", "guest", "winner", "updated_at"])
    else:
        record = MatchRecord.objects.create(
            host=solo_system_user,
            guest=ai_user,
            status="active",
            game_state=_build_new_match_state(cards, difficulty=difficulty),
        )

    request.session[SESSION_MATCH_KEY] = record.room_code
    request.session.modified = True
    return JsonResponse({"ok": True, **_match_payload(record)})


@require_GET
def get_match(request, room_code):
    record, error_response = _get_session_match_or_error(request, room_code)
    if error_response:
        return error_response
    _, state_error = _validated_record_state(record)
    if state_error:
        return state_error
    return JsonResponse({"ok": True, **_match_payload(record)})


@require_http_methods(["POST"])
def match_action(request, room_code):
    record, error_response = _get_session_match_or_error(request, room_code)
    if error_response:
        return error_response

    state, state_error = _validated_record_state(record)
    if state_error:
        return state_error

    payload = _payload(request)
    payload_error = _validate_action_payload(payload)
    if payload_error:
        return _json_error(payload_error)

    error = _apply_action(state, "host", payload)
    if error:
        return _json_error(error)

    _ai_turn(state)
    if state.get("winner"):
        record.status = "finished"
    record.game_state = state
    record.save(update_fields=["game_state", "status", "updated_at"])
    return JsonResponse({"ok": True, **_match_payload(record)})
