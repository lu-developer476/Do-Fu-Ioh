import json

from django.test import TestCase

from .models import MonsterCard


class SoloAIModeTests(TestCase):
    def setUp(self):
        for family in ['Pios', 'Escarahojas', 'Gelatinas', 'Kitsus']:
            for idx in range(3):
                MonsterCard.objects.create(
                    family=family,
                    name=f'{family} Carta {idx}',
                    slug=f'{family.lower()}-carta-{idx}',
                    stage='base',
                    level_min=1,
                    level_max=2,
                    hp=6,
                    shell=1,
                    action_points=2,
                    movement_points=2,
                    description='test',
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

        summon = self.client.post(
            f'/api/match/{room_code}/action/',
            data=json.dumps({'action': 'summon', 'hand_index': 0, 'x': center_x, 'y': 0}),
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
