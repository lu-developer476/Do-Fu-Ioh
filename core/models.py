import random
import string

from django.contrib.auth.models import User
from django.db import models


def default_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar_url = models.URLField(blank=True, default='')

    def __str__(self):
        return f'Perfil de {self.user.username}'


class MonsterCard(models.Model):
    STAGES = [
        ('base', 'Base'),
        ('fusion', 'Fusión'),
        ('evolution', 'Evolución'),
    ]

    family = models.CharField(max_length=40, db_index=True)
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    stage = models.CharField(max_length=20, choices=STAGES)
    level_min = models.PositiveIntegerField(default=1)
    level_max = models.PositiveIntegerField(default=1)
    hp = models.PositiveIntegerField()
    shell = models.PositiveIntegerField(default=0)
    action_points = models.PositiveIntegerField(default=1)
    movement_points = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True, default='')
    image = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['family', 'stage', 'name']

    def __str__(self):
        return self.name


class Deck(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='decks')
    name = models.CharField(max_length=60)
    cards = models.ManyToManyField(MonsterCard, through='DeckEntry', related_name='decks')
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user.username}: {self.name}'


class DeckEntry(models.Model):
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name='entries')
    card = models.ForeignKey(MonsterCard, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('deck', 'card')

    def __str__(self):
        return f'{self.deck.name} - {self.card.name} x{self.quantity}'


class MatchRecord(models.Model):
    room_code = models.CharField(max_length=16, db_index=True, default=default_room_code, unique=True)
    host = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hosted_matches')
    guest = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='guest_matches')
    status = models.CharField(max_length=20, default='waiting')
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_matches')
    game_state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'Partida {self.room_code} - {self.status}'
