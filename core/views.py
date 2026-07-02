import json
import random
import secrets

from django.db import connection, transaction
from django.db.utils import DatabaseError, OperationalError, ProgrammingError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .card_catalog import (
    resolve_card_image as catalog_resolve_card_image,
    serialized_cards_queryset,
    serialized_cards_seed_data,
    summon_cost,
)
from .models import MatchRecord, MonsterCard
from .system_users import get_single_player_system_users

ARENA_SLOTS = 5
LEGACY_BOARD_WIDTH = ARENA_SLOTS
LEGACY_BOARD_HEIGHT = 9
HAND_SIZE = 5
DECK_SIZE = 12
MAX_ENERGY = 10
AI_DIFFICULTIES = {"normal", "extremo"}
STAGE_RANK = {"base": 0, "fusion": 1, "evolution": 2}
SUPPORTED_ACTIONS = {"summon", "attack", "end_turn"}
ACTION_FIELD_TYPES = {
    "summon": {"hand_index": int, "slot": int},
    "attack": {"attacker_id": str, "target_id": str},
    "end_turn": {},
}
SESSION_MATCH_KEY = "active_ai_match_room_code"


def _json_error(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


def _payload(request):
    try:
        return json.loads((request.body or b"{}").decode("utf-8")), None
    except json.JSONDecodeError:
        return None, _json_error("JSON inválido.", status=400)


def _normalize_ai_difficulty(value):
    difficulty = (value or "normal").strip().lower()
    return difficulty if difficulty in AI_DIFFICULTIES else "normal"


def _resolve_card_image(image):
    return catalog_resolve_card_image(image)


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
        "summon_cost": summon_cost({"stage": card.stage}),
    }


def _build_deck(serialized_cards):
    deck = list(serialized_cards)
    random.shuffle(deck)
    return deck


def _player_state(side, deck_cards, draw_all=False, shuffle=True):
    if shuffle:
        random.shuffle(deck_cards)
    initial_hand_size = len(deck_cards) if draw_all else HAND_SIZE
    hand = deck_cards[:initial_hand_size]
    library = deck_cards[initial_hand_size:]
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


def _empty_match_state(difficulty):
    return {
        "mode": "vs_ai",
        "ai_difficulty": difficulty,
        "arena": {"slots": ARENA_SLOTS},
        "turn": {"number": 1, "active_side": "host"},
        "host": _player_state("host", []),
        "guest": _player_state("guest", []),
        "winner": None,
        "log": ["No hay cartas cargadas en la base de datos."],
    }


def _selected_cards_first(cards, selected_card_ids=None):
    selected_ids = {str(card_id) for card_id in selected_card_ids or []}
    if not selected_ids:
        return list(cards)
    selected = [card for card in cards if str(card.get("id")) in selected_ids]
    remaining = [card for card in cards if str(card.get("id")) not in selected_ids]
    return selected + remaining


def _available_serialized_cards():
    try:
        return serialized_cards_queryset()
    except (DatabaseError, OperationalError, ProgrammingError):
        return serialized_cards_seed_data()


def _build_new_match_state(cards, difficulty="normal", selected_card_ids=None):
    difficulty = _normalize_ai_difficulty(difficulty)
    serialized = _selected_cards_first(cards, selected_card_ids)
    if not serialized:
        return _empty_match_state(difficulty)
    return {
        "mode": "vs_ai",
        "ai_difficulty": difficulty,
        "arena": {"slots": ARENA_SLOTS},
        "turn": {"number": 1, "active_side": "host"},
        "host": _player_state(
            "host",
            (
                _selected_cards_first(serialized, selected_card_ids)
                if selected_card_ids
                else _build_deck(serialized)
            ),
            draw_all=True,
            shuffle=False,
        ),
        "guest": _player_state("guest", _build_deck(serialized), draw_all=True),
        "winner": None,
        "log": [
            "Duelo iniciado con el catálogo disponible.",
            "La mano del jugador respeta la selección manual cuando fue indicada.",
        ],
    }


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


def _validate_unit_payload(unit, side, index, slots):
    context = f"{side}.units[{index}]"
    if not isinstance(unit, dict):
        return f"{context} debe ser un objeto."
    if not isinstance(unit.get("id"), str) or not unit["id"].strip():
        return f"{context}.id es obligatorio."
    if unit.get("owner") != side:
        return f"{context}.owner debe ser '{side}'."
    if not isinstance(unit.get("slot"), int) or not 0 <= unit["slot"] < slots:
        return f"{context}.slot debe estar dentro de la arena."
    card_error = _validate_card_payload(unit.get("card"), f"{context}.card")
    if card_error:
        return card_error
    for field in ("hp_current", "shell_current", "pa_current", "summoned_turn"):
        if not _is_non_negative_int(unit.get(field)):
            return f"{context}.{field} debe ser un entero mayor o igual a 0."
    if not isinstance(unit.get("can_act"), bool):
        return f"{context}.can_act debe ser booleano."
    return None


def _validate_player_state(player, side, slots):
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
    if player["hand_count"] != len(player["hand"]):
        return f"{side}.hand_count no coincide con hand."
    if player["library_count"] != len(player["library"]):
        return f"{side}.library_count no coincide con library."
    for index, card in enumerate(player["hand"] + player["library"]):
        card_error = _validate_card_payload(card, f"{side}.cards[{index}]")
        if card_error:
            return card_error
    for index, unit in enumerate(player["units"]):
        unit_error = _validate_unit_payload(unit, side, index, slots)
        if unit_error:
            return unit_error
    if player["energy"] > player["max_energy"]:
        return f"{side}.energy no puede superar max_energy."
    return None



def _coerce_legacy_card_arena_state(state):
    """Acepta partidas previas con tablero y las proyecta a slots de cartas."""
    if not isinstance(state, dict):
        return state
    state.setdefault("arena", {"slots": ARENA_SLOTS})
    state.setdefault("board", {"width": LEGACY_BOARD_WIDTH, "height": LEGACY_BOARD_HEIGHT})
    if "slots" not in state["arena"]:
        state["arena"]["slots"] = ARENA_SLOTS
    slots = state["arena"]["slots"]
    for side in ("host", "guest"):
        player = state.get(side)
        if not isinstance(player, dict):
            continue
        used = set()
        for unit in player.get("units", []):
            if not isinstance(unit, dict):
                continue
            raw_slot = unit.get("slot")
            if not isinstance(raw_slot, int):
                raw_slot = unit.get("x", 0)
            slot = raw_slot % slots
            while slot in used and len(used) < slots:
                slot = (slot + 1) % slots
            unit["slot"] = slot
            used.add(slot)
            unit.setdefault("pa_current", unit.get("card", {}).get("action_points", 0))
            unit.setdefault("can_act", True)
    return state

def _validate_match_state(state):
    state = _coerce_legacy_card_arena_state(state)
    if not isinstance(state, dict):
        return "la raíz debe ser un objeto JSON."
    arena = state.get("arena")
    if not isinstance(arena, dict) or not isinstance(arena.get("slots"), int) or arena["slots"] <= 0:
        return "arena.slots debe ser un entero positivo."
    turn = state.get("turn")
    if not isinstance(turn, dict):
        return "turn debe ser un objeto."
    if not _is_non_negative_int(turn.get("number")) or turn["number"] <= 0:
        return "turn.number debe ser un entero positivo."
    if turn.get("active_side") not in {"host", "guest"}:
        return "turn.active_side debe ser 'host' o 'guest'."
    slots = arena["slots"]
    for side in ("host", "guest"):
        player_error = _validate_player_state(state.get(side), side, slots)
        if player_error:
            return player_error
        player_slots = [unit["slot"] for unit in state[side]["units"]]
        if len(player_slots) != len(set(player_slots)):
            return f"{side} tiene cartas superpuestas en la arena."
    unit_ids = [unit["id"] for side in ("host", "guest") for unit in state[side]["units"]]
    if len(unit_ids) != len(set(unit_ids)):
        return "hay unidades con id duplicado."
    if state.get("winner") not in {None, "host", "guest"}:
        return "winner debe ser null, 'host' o 'guest'."
    if not isinstance(state.get("log"), list) or any(not isinstance(item, str) for item in state["log"]):
        return "log sólo puede contener textos."
    return None


def _validate_action_payload(payload):
    if not isinstance(payload, dict):
        return "El cuerpo de la acción debe ser un objeto JSON."
    action = payload.get("action")
    if action not in SUPPORTED_ACTIONS:
        return "Acción no soportada."
    for field, expected_type in ACTION_FIELD_TYPES[action].items():
        if action == "summon" and field == "slot" and "slot" not in payload and isinstance(payload.get("x"), int):
            continue
        value = payload.get(field)
        if expected_type is int and not isinstance(value, int):
            return f"El campo '{field}' debe ser un entero."
        if expected_type is str and (not isinstance(value, str) or not value.strip()):
            return f"El campo '{field}' debe ser un texto no vacío."
    return None


def _append_log(state, message):
    state["log"].append(message)
    state["log"] = state["log"][-12:]


def _draw_one(player):
    if player["library"]:
        player["hand"].append(player["library"].pop(0))


def _refresh_counts(state):
    for side in ("host", "guest"):
        state[side]["library_count"] = len(state[side]["library"])
        state[side]["hand_count"] = len(state[side]["hand"])


def _find_unit(player, unit_id):
    return next((unit for unit in player["units"] if unit["id"] == unit_id), None)


def _open_slots(player, slots):
    occupied = {unit["slot"] for unit in player["units"]}
    return [slot for slot in range(slots) if slot not in occupied]


def _attack_range(unit):
    return min(5, 1 + STAGE_RANK.get(unit["card"].get("stage"), 0) + unit["card"].get("action_points", 0) // 2)


def _attackable_unit_ids(state, attacker, enemy_side=None):
    if attacker["pa_current"] <= 0 or not attacker["can_act"]:
        return []
    side = enemy_side or ("guest" if attacker["owner"] == "host" else "host")
    # Sin tablero: las cartas combaten desde una arena abstracta. La columna/slot afecta prioridad visual,
    # no bloquea objetivos, así el foco queda en estadísticas y características de cada monstruo.
    return sorted(unit["id"] for unit in state[side]["units"])


def _state_for_client(state):
    state = _coerce_legacy_card_arena_state(state)
    payload = json.loads(json.dumps(state))
    payload.setdefault("board", {"width": LEGACY_BOARD_WIDTH, "height": LEGACY_BOARD_HEIGHT})
    for side in ("host", "guest"):
        enemy_side = "guest" if side == "host" else "host"
        for unit in payload.get(side, {}).get("units", []):
            unit["attack_range"] = _attack_range(unit)
            unit["attackable_unit_ids"] = _attackable_unit_ids(payload, unit, enemy_side=enemy_side)
    return payload


def _build_unit_from_card(state, side, card, slot):
    return {
        "id": secrets.token_hex(6),
        "owner": side,
        "slot": slot,
        "x": slot,
        "y": 0 if side == "host" else LEGACY_BOARD_HEIGHT - 1,
        "card": card,
        "hp_current": card["hp"],
        "shell_current": card["shell"],
        "pa_current": card["action_points"],
        "can_act": True,
        "summoned_turn": state["turn"]["number"],
    }


def _apply_summon_action(state, side, actor, payload):
    hand_index = payload.get("hand_index")
    slot = payload.get("slot")
    slots = state["arena"]["slots"]
    if slot is None and isinstance(payload.get("x"), int):
        slot = payload["x"] % slots
    if hand_index < 0 or hand_index >= len(actor["hand"]):
        return "Carta inválida."
    if slot < 0 or slot >= slots:
        return "Slot inválido."
    if slot not in _open_slots(actor, slots):
        return "Ese slot ya está ocupado."
    if actor["summons_this_turn"] >= 1:
        return "Ya invocaste este turno."
    card = actor["hand"].pop(hand_index)
    cost = summon_cost(card)
    if actor["energy"] < cost:
        actor["hand"].insert(hand_index, card)
        return "No alcanza la energía para invocar."
    actor["energy"] -= cost
    actor["summons_this_turn"] += 1
    actor["units"].append(_build_unit_from_card(state, side, card, slot))
    _append_log(state, f"{side} invocó {card['name']} en el slot {slot + 1}.")
    return None


def _apply_attack_action(state, side, actor, enemy, payload):
    attacker = _find_unit(actor, payload.get("attacker_id"))
    target = _find_unit(enemy, payload.get("target_id"))
    if not attacker or not target:
        return "Ataque inválido."
    if target["id"] not in _attackable_unit_ids(state, attacker, enemy_side=target["owner"]):
        return "Objetivo inválido o sin PA."
    attacker["pa_current"] -= 1
    attacker["can_act"] = attacker["pa_current"] > 0
    attack_power = attacker["card"]["action_points"] + 2 + STAGE_RANK.get(attacker["card"]["stage"], 0)
    absorbed = min(target["shell_current"], max(0, attack_power - 1))
    target["shell_current"] = max(0, target["shell_current"] - absorbed)
    damage = max(1, attack_power - absorbed)
    target["hp_current"] -= damage
    _append_log(state, f"{side} atacó con {attacker['card']['name']} e infligió {damage} de daño.")
    if target["hp_current"] <= 0:
        enemy["units"] = [unit for unit in enemy["units"] if unit["id"] != target["id"]]
        _append_log(state, f"{target['card']['name']} fue derrotado.")
    return None


def _reset_turn_state(player):
    player["summons_this_turn"] = 0
    for unit in player["units"]:
        unit["pa_current"] = unit["card"]["action_points"]
        unit["can_act"] = True


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


def _player_has_remaining_resources(player):
    return bool(player["units"] or player["hand"] or player["library"])


def _update_winner_for_current_mode(state, acting_side):
    host_still = _player_has_remaining_resources(state["host"])
    guest_still = _player_has_remaining_resources(state["guest"])
    if host_still and guest_still:
        return
    state["winner"] = "host" if host_still else "guest" if guest_still else acting_side


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
        "attack": lambda: _apply_attack_action(state, side, actor, enemy, payload),
        "end_turn": lambda: _apply_end_turn_action(state, side, enemy_side, enemy),
    }
    error = handlers[action]()
    if error:
        return error
    _update_winner_for_current_mode(state, side)
    _refresh_counts(state)
    return None


def _select_attack_target(state, unit, difficulty):
    ids = _attackable_unit_ids(state, unit, enemy_side="host")
    if not ids:
        return None
    host_units = {unit["id"]: unit for unit in state["host"]["units"]}
    attack_power = unit["card"]["action_points"] + 2 + STAGE_RANK.get(unit["card"]["stage"], 0)
    def score(target):
        damage = max(1, attack_power - min(target["shell_current"], max(0, attack_power - 1)))
        lethal = target["hp_current"] <= damage
        return (1 if lethal else 0, damage, target["card"]["action_points"], -target["hp_current"])
    return max((host_units[target_id] for target_id in ids), key=score)


def _best_summon_action(state, difficulty):
    ai = state["guest"]
    affordable = [(index, card) for index, card in enumerate(ai["hand"]) if summon_cost(card) <= ai["energy"]]
    if not affordable or ai["summons_this_turn"] >= 1:
        return None
    open_slots = _open_slots(ai, state["arena"]["slots"])
    if not open_slots:
        return None
    def card_priority(item):
        _, card = item
        return (STAGE_RANK.get(card["stage"], 0), card["action_points"], card["hp"], card["shell"], -summon_cost(card))
    preferred_order = [2, 1, 3, 0, 4]
    slot = next((slot for slot in preferred_order if slot in open_slots), open_slots[0])
    index, _ = max(affordable, key=card_priority)
    return {"action": "summon", "hand_index": index, "slot": slot}


def _ai_turn(state):
    _coerce_legacy_card_arena_state(state)
    if state["turn"]["active_side"] != "guest" or state["winner"]:
        return
    difficulty = _normalize_ai_difficulty(state.get("ai_difficulty"))
    summon_action = _best_summon_action(state, difficulty)
    if summon_action:
        _apply_action(state, "guest", summon_action)
    for unit in list(state["guest"]["units"]):
        while unit.get("can_act") and not state.get("winner"):
            target = _select_attack_target(state, unit, difficulty)
            if not target:
                break
            _apply_action(state, "guest", {"action": "attack", "attacker_id": unit["id"], "target_id": target["id"]})
    if not state["winner"]:
        _apply_action(state, "guest", {"action": "end_turn"})


def _match_payload(record):
    state = _state_for_client(record.game_state or {})
    return {"room_code": record.room_code, "status": record.status, "match": {"room_code": record.room_code, **state}}


def _clear_active_match_session(request):
    request.session.pop(SESSION_MATCH_KEY, None)
    request.session.modified = True


def _active_match_from_session(request):
    room_code = request.session.get(SESSION_MATCH_KEY)
    if not room_code:
        return None
    try:
        return MatchRecord.objects.get(room_code=room_code, status="active")
    except MatchRecord.DoesNotExist:
        _clear_active_match_session(request)
        return None


def _get_session_match_or_error(request, room_code):
    session_room = request.session.get(SESSION_MATCH_KEY)
    if not session_room or session_room != room_code:
        if session_room and session_room != room_code:
            _clear_active_match_session(request)
        return None, _json_error("Partida no disponible para esta sesión.", status=404)
    try:
        return MatchRecord.objects.get(room_code=room_code, status="active"), None
    except MatchRecord.DoesNotExist:
        _clear_active_match_session(request)
        return None, _json_error("La partida no existe o ya no está activa.", status=404)


def _validated_record_state(record):
    state = record.game_state or {}
    state_error = _validate_match_state(state)
    if state_error:
        return None, _json_error(f"Estado de partida inválido: {state_error}", status=500)
    return state, None


def _persist_record_state(record, state):
    record.game_state = state
    record.status = "finished" if state.get("winner") else "active"
    winner_side = state.get("winner")
    record.winner = getattr(record, winner_side, None) if winner_side in {"host", "guest"} else None
    record.save(update_fields=["game_state", "status", "winner", "updated_at"])


@require_GET
@ensure_csrf_cookie
def index(request):
    return render(request, "core/index.html", {"cards_seed_json": serialized_cards_seed_data()})


@require_GET
def health(request):
    return JsonResponse({"ok": True, "mode": "backendless", "checks": {"app": True, "database": "disabled"}})


@require_GET
def cards_catalog(request):
    return JsonResponse({"ok": True, "cards": serialized_cards_seed_data(), "source": "seed"})


def _backendless_api_disabled(*_args, **_kwargs):
    return JsonResponse(
        {
            "ok": False,
            "message": "El duelo vs IA ahora corre 100% en el navegador; esta API ya no persiste partidas.",
        },
        status=410,
    )


get_active_match = _backendless_api_disabled
create_match_vs_ai = _backendless_api_disabled
get_match = _backendless_api_disabled
match_action = _backendless_api_disabled
