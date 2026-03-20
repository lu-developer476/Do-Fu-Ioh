from django.core.management.base import BaseCommand

from ...card_catalog import sync_monster_cards


class Command(BaseCommand):
    help = 'Seed inicial del catálogo de cartas si la tabla MonsterCard está vacía.'

    def handle(self, *args, **options):
        created = sync_monster_cards()
        if created:
            self.stdout.write(self.style.SUCCESS(f'Se cargaron {created} cartas.'))
            return
        self.stdout.write('No se cargaron cartas: el catálogo ya existía o no había datos disponibles.')
