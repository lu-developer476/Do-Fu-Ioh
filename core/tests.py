from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, TestCase

from .card_catalog import CardSeedDataError, load_cards_seed_data, serialized_cards_seed_data


class CardSeedSourceValidationTests(SimpleTestCase):
    def test_load_cards_seed_data_rejects_invalid_json(self):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / 'cards.json'
            path.write_text('{bad json', encoding='utf-8')

            with self.assertRaises(CardSeedDataError):
                load_cards_seed_data(path=path)

    def test_base_escarahojas_match_reference_stats(self):
        cards = {card['name']: card for card in load_cards_seed_data()}
        names = [
            'Escarahoja anaranjada',
            'Escarahoja limonada',
            'Escarahoja sonrosada',
            'Escarahoja tostada',
            'Escarahoja violeta',
        ]

        for name in names:
            with self.subTest(name=name):
                card = cards[name]
                self.assertEqual(card['stage'], 'base')
                self.assertEqual(card['level_min'], 36)
                self.assertEqual(card['level_max'], 48)
                self.assertEqual(card['hp_min'], 320)
                self.assertEqual(card['hp_max'], 450)
                self.assertEqual(card['hp'], 450)
                self.assertEqual(card['shell'], 120)
                self.assertEqual(card['action_points'], 7)
                self.assertEqual(card['movement_points'], 4)


class KitsuCatalogDataTests(SimpleTestCase):
    def test_kitsu_fusions_match_reference_stats(self):
        cards = {card['name']: card for card in load_cards_seed_data()}

        expected = {
            'Kitsu nishiki': (135, 1800, 450, 8, 5),
            'Kitsu penta': (135, 1800, 450, 8, 5),
            'Kitsu yin yang': (135, 1800, 450, 8, 5),
        }

        for name, (level, hp, shell, action_points, movement_points) in expected.items():
            with self.subTest(card=name):
                card = cards[name]
                self.assertEqual(card['stage'], 'fusion')
                self.assertEqual(card['level_min'], level)
                self.assertEqual(card['level_max'], level)
                self.assertEqual(card['hp'], hp)
                self.assertEqual(card['shell'], shell)
                self.assertEqual(card['action_points'], action_points)
                self.assertEqual(card['movement_points'], movement_points)

    def test_kitsu_evolutions_match_reference_stats(self):
        cards = {card['name']: card for card in load_cards_seed_data()}

        expected = {
            'Kitsu silvestre evolucionado': (178, 2250, 550, 10, 7),
            'Kitsu kumiawase': (178, 2250, 550, 10, 7),
            'Kitsu nishiki evolucionado': (178, 2250, 550, 10, 7),
            'Kitsu penta evolucionado': (178, 2250, 550, 10, 7),
            'Kitsu yin yang evolucionado': (178, 2250, 550, 10, 7),
        }

        for name, (level, hp, shell, action_points, movement_points) in expected.items():
            with self.subTest(card=name):
                card = cards[name]
                self.assertEqual(card['stage'], 'evolution')
                self.assertEqual(card['level_min'], level)
                self.assertEqual(card['level_max'], level)
                self.assertEqual(card['hp'], hp)
                self.assertEqual(card['shell'], shell)
                self.assertEqual(card['action_points'], action_points)
                self.assertEqual(card['movement_points'], movement_points)

    def test_kitsu_reference_spells_are_defined(self):
        cards = {card['name']: card for card in serialized_cards_seed_data()}
        kitsus = [card for card in cards.values() if card['family'] == 'Kitsus']

        for card in kitsus:
            spell_suffix = card['name'].removeprefix('Kitsu ')

            with self.subTest(card=card['name']):
                self.assertEqual(
                    [spell['name'] for spell in card['spells']],
                    [
                        f'Kitsinición {spell_suffix}',
                        f'Ilusión espectral {spell_suffix}',
                        f'Argucia del Kitsu {spell_suffix}',
                    ],
                )
                self.assertEqual(len(card['spells']), 3)
                for spell in card['spells']:
                    self.assertIn('cost', spell)
                    self.assertIn('range', spell)


class BackendlessModeTests(TestCase):
    def test_index_bootstraps_seed_cards_for_local_gameplay(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cards-seed')
        self.assertContains(response, 'Modo sin Backend activo')
        self.assertContains(response, 'Nuevo duelo')

    def test_frontend_keeps_catalog_and_arena_renderers(self):
        script = Path(__file__).resolve().parent / 'static' / 'core' / 'js' / 'game.js'
        source = script.read_text(encoding='utf-8')

        self.assertIn('function renderCatalog()', source)
        self.assertIn('function renderArenaRow(', source)
        self.assertIn('function renderArenaCard(', source)

    def test_health_does_not_depend_on_database(self):
        response = self.client.get('/health/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'backendless')
        self.assertEqual(response.json()['checks']['database'], 'disabled')

    def test_cards_endpoint_serves_static_seed_catalog_only(self):
        response = self.client.get('/api/cards/')

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['source'], 'seed')
        self.assertGreater(len(payload['cards']), 0)
        self.assertIn('summon_cost', payload['cards'][0])

    def test_seed_catalog_marks_summons_as_free(self):
        response = self.client.get('/api/cards/')

        payload = response.json()
        self.assertTrue(all(card['summon_cost'] == 0 for card in payload['cards']))

    def test_frontend_allows_multiple_free_summons_for_player_and_ai(self):
        script = Path(__file__).resolve().parent / 'static' / 'core' / 'js' / 'game.js'
        source = script.read_text(encoding='utf-8')

        self.assertIn('function summonCost(card = {}) { return FREE_SUMMON_COST; }', source)
        self.assertIn("while (ai.hand.length && deployCells('guest').length)", source)
        self.assertNotIn('No alcanza la energía para invocar.', source)
        self.assertNotIn('Ya invocaste este turno.', source)

    def test_match_apis_are_disabled_in_backendless_mode(self):
        response = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json')

        self.assertEqual(response.status_code, 410)
        self.assertIn('navegador', response.json()['message'])
