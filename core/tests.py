import json

from django.middleware.csrf import _get_new_csrf_string
from django.test import Client, TestCase

from .models import MonsterCard


class SoloAIModeTests(TestCase):
    def setUp(self):
        for family in ['Pios', 'Escarahojas', 'Gelatinas', 'Kitsus']:
            for idx in range(3):
                MonsterCard.objects.create(
                    family=family,
                    name=f'{family} Carta {idx}',
                    slug=f'{family.lower()}-carta-{idx}',
                    stage='base' if idx == 0 else 'fusion' if idx == 1 else 'evolution',
                    level_min=1,
                    level_max=2,
                    hp=6,
                    shell=1,
                    action_points=2,
                    movement_points=2,
                    description='test',
                    image='public/images/pios/base/pio-albino.png',
                )

    def test_create_match_and_recover_from_session(self):
        created = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json')
        self.assertEqual(created.status_code, 200)
        payload = created.json()
        self.assertEqual(payload['match']['mode'], 'vs_ai')
        self.assertEqual(payload['match']['turn']['active_side'], 'host')

        active = self.client.get('/api/match/active/')
        self.assertEqual(active.status_code, 200)
        self.assertEqual(active.json()['room_code'], payload['room_code'])

    def test_session_is_required_for_match_access(self):
        created = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json').json()
        room_code = created['room_code']

        ok = self.client.get(f'/api/match/{room_code}/')
        self.assertEqual(ok.status_code, 200)

        other_client = self.client_class()
        denied = other_client.get(f'/api/match/{room_code}/')
        self.assertEqual(denied.status_code, 404)

    def test_turn_actions_work_without_user_login(self):
        created = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json').json()
        room_code = created['room_code']
        center_x = created['match']['board']['width'] // 2
        hand = created['match']['host']['hand']
        playable_index = next(index for index, card in enumerate(hand) if card['summon_cost'] <= 1)

        summon = self.client.post(
            f'/api/match/{room_code}/action/',
            data=json.dumps({'action': 'summon', 'hand_index': playable_index, 'x': center_x, 'y': 0}),
            content_type='application/json',
        )
        self.assertEqual(summon.status_code, 200)

        end_turn = self.client.post(
            f'/api/match/{room_code}/action/',
            data=json.dumps({'action': 'end_turn'}),
            content_type='application/json',
        )
        self.assertEqual(end_turn.status_code, 200)
        state = end_turn.json()['match']
        self.assertEqual(state['turn']['active_side'], 'host')
        self.assertTrue(any('Fin del turno' in item for item in state['log']))

    def test_cards_expose_resolved_images_and_summon_cost(self):
        response = self.client.get('/api/cards/')
        self.assertEqual(response.status_code, 200)
        card = response.json()['cards'][0]
        self.assertTrue(card['image'].startswith('/static/'))
        self.assertIn(card['summon_cost'], {1, 3, 5})

    def test_match_actions_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        without_csrf = client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json')
        self.assertEqual(without_csrf.status_code, 403)

        csrf_token = _get_new_csrf_string()
        client.cookies['csrftoken'] = csrf_token
        with_csrf = client.post(
            '/api/match/create-vs-ai/',
            data='{}',
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(with_csrf.status_code, 200)
