from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, TestCase

from .card_catalog import CardSeedDataError, load_cards_seed_data


class CardSeedSourceValidationTests(SimpleTestCase):
    def test_load_cards_seed_data_rejects_invalid_json(self):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / 'cards.json'
            path.write_text('{bad json', encoding='utf-8')

            with self.assertRaises(CardSeedDataError):
                load_cards_seed_data(path=path)


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
