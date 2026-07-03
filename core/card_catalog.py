import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS
from django.db.utils import OperationalError, ProgrammingError
from django.utils.text import slugify

from .models import MonsterCard

logger = logging.getLogger(__name__)

CARDS_DATA_PATH = Path(settings.BASE_DIR) / 'data' / 'cards.json'
SUMMON_COST_BY_STAGE = {
    'base': 0,
    'fusion': 0,
    'evolution': 0,
}
OPTIONAL_CARD_DEFAULTS = {
    'description': '',
    'image': '',
    'shell': 0,
    'action_points': 1,
    'movement_points': 1,
    'hp_min': None,
    'hp_max': None,
    'spells': [],
}
REQUIRED_CARD_FIELDS = (
    'name',
    'family',
    'stage',
    'level_min',
    'level_max',
    'hp',
)
VALID_CARD_STAGES = frozenset(SUMMON_COST_BY_STAGE)


@dataclass
class CardImportStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0


class CardSeedDataError(ValueError):
    """Raised when the cards seed source cannot be parsed safely."""


def slugify_card_name(value: str) -> str:
    return slugify((value or '').strip(), allow_unicode=False)[:140]


def resolve_card_image(image: str) -> str:
    raw = (image or '').strip()
    if not raw:
        return ''
    if raw.startswith(('http://', 'https://', '/')):
        return raw
    cleaned = raw[7:] if raw.startswith('public/') else raw
    return f'/static/{cleaned}'


def summon_cost(card_like) -> int:
    stage = card_like.get('stage', 'base')
    return SUMMON_COST_BY_STAGE.get(stage, 0)


@lru_cache(maxsize=1)
def seed_spells_by_slug(path=CARDS_DATA_PATH):
    spells = {}
    for item in load_cards_seed_data(path=path):
        try:
            slug, payload = _normalized_card_payload(item)
        except ValueError:
            continue
        spells[slug] = payload['spells']
    return spells


def serialize_card(card: MonsterCard) -> dict:
    return {
        'id': card.id,
        'name': card.name,
        'slug': card.slug,
        'family': card.family,
        'stage': card.stage,
        'level_min': card.level_min,
        'level_max': card.level_max,
        'hp': card.hp,
        'hp_min': card.hp,
        'hp_max': card.hp,
        'shell': card.shell,
        'action_points': card.action_points,
        'movement_points': card.movement_points,
        'description': card.description,
        'image': resolve_card_image(card.image),
        'summon_cost': summon_cost({'stage': card.stage}),
        'spells': seed_spells_by_slug().get(card.slug, []),
    }


def serialize_seed_card(item: dict, card_id: int) -> dict:
    slug, payload = _normalized_card_payload(item)
    return {
        'id': card_id,
        'slug': slug,
        **payload,
        'image': resolve_card_image(payload['image']),
        'summon_cost': summon_cost(payload),
    }


def serialized_cards_queryset():
    return [serialize_card(card) for card in MonsterCard.objects.all()]


def serialized_cards_seed_data(path=CARDS_DATA_PATH):
    cards = []
    for index, item in enumerate(load_cards_seed_data(path=path), start=1):
        try:
            cards.append(serialize_seed_card(item, index))
        except ValueError as exc:
            logger.warning('Skipping invalid seed card #%s: %s', index, exc)
    return cards


def load_cards_seed_data(path=CARDS_DATA_PATH):
    if not path.exists():
        logger.warning('Cards seed file not found at %s', path)
        return []

    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise CardSeedDataError(f'JSON inválido en {path}: {exc.msg}.') from exc

    if not isinstance(payload, list):
        raise CardSeedDataError('El archivo de cartas debe contener una lista JSON.')

    return payload


def _normalized_card_payload(item):
    if not isinstance(item, dict):
        raise ValueError('cada carta debe ser un objeto JSON')

    missing_fields = [field for field in REQUIRED_CARD_FIELDS if item.get(field) in (None, '')]
    if missing_fields:
        raise ValueError(f"faltan campos requeridos: {', '.join(missing_fields)}")

    stage = str(item['stage']).strip()
    if stage not in VALID_CARD_STAGES:
        raise ValueError(f"stage inválido: {stage}")

    payload = {
        'family': str(item['family']).strip(),
        'name': str(item['name']).strip(),
        'stage': stage,
        'level_min': item['level_min'],
        'level_max': item['level_max'],
        'hp': item['hp'],
        'hp_min': item.get('hp_min', OPTIONAL_CARD_DEFAULTS['hp_min']),
        'hp_max': item.get('hp_max', OPTIONAL_CARD_DEFAULTS['hp_max']),
        'shell': item.get('shell', OPTIONAL_CARD_DEFAULTS['shell']),
        'action_points': item.get('action_points', OPTIONAL_CARD_DEFAULTS['action_points']),
        'movement_points': item.get('movement_points', OPTIONAL_CARD_DEFAULTS['movement_points']),
        'description': item.get('description', OPTIONAL_CARD_DEFAULTS['description']),
        'image': item.get('image', OPTIONAL_CARD_DEFAULTS['image']),
        'spells': item.get('spells', OPTIONAL_CARD_DEFAULTS['spells']),
    }

    if not isinstance(payload['spells'], list):
        raise ValueError('spells debe ser una lista')
    for index, spell in enumerate(payload['spells'], start=1):
        if not isinstance(spell, dict):
            raise ValueError(f'spells[{index}] debe ser un objeto')
        for field in ('damage_min', 'damage_max'):
            if not isinstance(spell.get(field), int) or spell[field] <= 0:
                raise ValueError(f'spells[{index}].{field} debe ser un entero mayor a 0')
        if spell['damage_max'] < spell['damage_min']:
            raise ValueError(f'spells[{index}].damage_max no puede ser menor que damage_min')

    integer_fields = ('level_min', 'level_max', 'hp', 'shell', 'action_points', 'movement_points')
    for field in integer_fields:
        if not isinstance(payload[field], int) or payload[field] < 0:
            raise ValueError(f'{field} debe ser un entero mayor o igual a 0')

    for field in ('hp_min', 'hp_max'):
        if payload[field] is not None and (not isinstance(payload[field], int) or payload[field] < 0):
            raise ValueError(f'{field} debe ser un entero mayor o igual a 0')

    if payload['hp_min'] is None:
        payload['hp_min'] = payload['hp']
    if payload['hp_max'] is None:
        payload['hp_max'] = payload['hp']
    if payload['hp_max'] < payload['hp_min']:
        raise ValueError('hp_max no puede ser menor que hp_min')
    if payload['hp'] < payload['hp_min'] or payload['hp'] > payload['hp_max']:
        raise ValueError('hp debe estar dentro del rango hp_min/hp_max')

    if payload['level_max'] < payload['level_min']:
        raise ValueError('level_max no puede ser menor que level_min')

    slug = slugify_card_name(payload['name'])
    if not slug:
        raise ValueError('no se pudo generar un slug válido')
    return slug, payload


def import_monster_cards(*, using=DEFAULT_DB_ALIAS, path=CARDS_DATA_PATH, stdout=None):
    stats = CardImportStats()

    try:
        MonsterCard.objects.using(using).exists()
    except (ProgrammingError, OperationalError):
        return stats

    source_data = load_cards_seed_data(path=path)
    for index, item in enumerate(source_data, start=1):
        try:
            slug, defaults = _normalized_card_payload(item)
        except ValueError as exc:
            stats.skipped += 1
            if stdout:
                stdout.write(f"[WARN] Carta #{index} omitida: {exc}.")
            continue

        stats.processed += 1
        card, created = MonsterCard.objects.using(using).update_or_create(
            slug=slug,
            defaults={key: value for key, value in defaults.items() if key not in ('hp_min', 'hp_max', 'spells')},
        )
        if created:
            stats.created += 1
            if stdout:
                stdout.write(f"[CREATE] {card.name} ({card.slug})")
            continue

        stats.updated += 1
        if stdout:
            stdout.write(f"[UPDATE] {card.name} ({card.slug})")

    return stats
