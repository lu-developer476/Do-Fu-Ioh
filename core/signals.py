from django.apps import apps
from django.contrib.auth.models import User
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .card_catalog import sync_monster_cards
from .models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_migrate)
def seed_cards_catalog(sender, app_config, using, **kwargs):
    core_config = apps.get_app_config('core')
    if app_config != core_config:
        return
    sync_monster_cards(using=using)
