import json
import unicodedata
from pathlib import Path

from django.conf import settings

from .models import MonsterCard


def _slugify(value: str) -> str:
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = ''.join(ch.lower() if ch.isalnum() else '-' for ch in value)
    value = '-'.join(part for part in value.split('-') if part)
    return value[:140]


def seed_cards(sender, **kwargs):
    data_path = Path(settings.BASE_DIR) / 'data' / 'cards.json'

    if not data_path.exists():
        return

    cards = json.loads(data_path.read_text(encoding='utf-8'))

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
