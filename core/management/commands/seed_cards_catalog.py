from django.core.management.base import BaseCommand, CommandError

from ...card_catalog import CardSeedDataError, import_monster_cards


class Command(BaseCommand):
    help = 'Carga o actualiza el catálogo de cartas desde data/cards.json.'

    def handle(self, *args, **options):
        self.stdout.write('[INFO] Iniciando importación de cartas desde data/cards.json...')
        try:
            stats = import_monster_cards(stdout=self.stdout)
        except CardSeedDataError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                '[DONE] Importación finalizada. '
                f'Procesadas: {stats.processed} | '
                f'Creadas: {stats.created} | '
                f'Actualizadas: {stats.updated} | '
                f'Omitidas: {stats.skipped}'
            )
        )
