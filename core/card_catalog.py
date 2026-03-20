import json
import logging
import unicodedata
from pathlib import Path

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS
from django.db.utils import OperationalError, ProgrammingError

from .models import MonsterCard

logger = logging.getLogger(__name__)

CARDS_DATA_PATH = Path(settings.BASE_DIR) / 'data' / 'cards.json'
SUMMON_COST_BY_STAGE = {
    'base': 1,
    'fusion': 3,
    'evolution': 5,
}


def slugify_card_name(value: str) -> str:
    value = (
        unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    )
    value = ''.join(ch.lower() if ch.isalnum() else '-' for ch in value)
    return '-'.join(part for part in value.split('-') if part)[:140]


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
    return SUMMON_COST_BY_STAGE.get(stage, 1)


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
        'shell': card.shell,
        'action_points': card.action_points,
        'movement_points': card.movement_points,
        'description': card.description,
        'image': resolve_card_image(card.image),
        'summon_cost': summon_cost({'stage': card.stage}),
    }


def serialized_cards_queryset():
    return [serialize_card(card) for card in MonsterCard.objects.all()]


def load_cards_seed_data():
    if not CARDS_DATA_PATH.exists():
        logger.warning('Cards seed file not found at %s', CARDS_DATA_PATH)
        return []
    return json.loads(CARDS_DATA_PATH.read_text(encoding='utf-8'))


def sync_monster_cards(*, using=DEFAULT_DB_ALIAS) -> int:
    try:
        existing = MonsterCard.objects.using(using).exists()
    except (ProgrammingError, OperationalError):
        return 0

    if existing:
        return 0

    created = 0
    for item in load_cards_seed_data():
        _, was_created = MonsterCard.objects.using(using).update_or_create(
            slug=slugify_card_name(item['name']),
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
        created += int(was_created)
    return created
