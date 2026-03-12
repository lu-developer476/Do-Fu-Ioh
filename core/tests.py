from django.contrib.auth.models import User
from django.test import TestCase

from .models import MonsterCard


class TacticalMatchFlowTests(TestCase):
    def setUp(self):
        for family in ['Píos', 'Escarahojas', 'Gelatinas', 'Kitsus']:
            for idx in range(3):
                MonsterCard.objects.create(
                    family=family,
                    name=f'{family} Base {idx}',
                    slug=f'{family.lower()}-base-{idx}'.replace('í', 'i'),
                    stage='base',
                    level_min=1,
                    level_max=2,
                    hp=5,
                    shell=1,
                    action_points=2,
                    movement_points=2,
                    description='test',
                )

        self.host = User.objects.create_user(username='host', password='123456')
        self.guest = User.objects.create_user(username='guest', password='123456')

    def test_match_uses_12x15_board(self):
        self.client.login(username='host', password='123456')
        response = self.client.post('/api/match/create/', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 201)
        state = response.json()['match']
        self.assertEqual(state['board']['width'], 12)
        self.assertEqual(state['board']['height'], 15)
        self.assertEqual(state['turn']['phase'], 'main')

    def test_phase_gates_actions(self):
        self.client.login(username='host', password='123456')
        create_response = self.client.post('/api/match/create/', data='{}', content_type='application/json')
        room_code = create_response.json()['room_code']
        self.client.logout()

        self.client.login(username='guest', password='123456')
        self.client.post(f'/api/match/{room_code}/join/', data='{}', content_type='application/json')
        self.client.logout()

        self.client.login(username='host', password='123456')
        state_response = self.client.get(f'/api/match/{room_code}/')
        hand = state_response.json()['match']['host']['hand']
        self.assertGreater(len(hand), 0)

        summon_response = self.client.post(
            f'/api/match/{room_code}/action/',
            data='{"action":"summon","hand_index":0,"x":0,"y":0}',
            content_type='application/json',
        )
        self.assertEqual(summon_response.status_code, 200)

        unit_id = summon_response.json()['match']['host']['units'][0]['id']
        attack_response = self.client.post(
            f'/api/match/{room_code}/action/',
            data=f'{{"action":"attack","attacker_id":"{unit_id}","target_id":"none"}}',
            content_type='application/json',
        )
        self.assertEqual(attack_response.status_code, 400)
        self.assertIn('fase de combate', attack_response.json()['message'])

        next_phase = self.client.post(
            f'/api/match/{room_code}/action/',
            data='{"action":"next_phase"}',
            content_type='application/json',
        )
        self.assertEqual(next_phase.status_code, 200)
        self.assertEqual(next_phase.json()['match']['turn']['phase'], 'combat')
