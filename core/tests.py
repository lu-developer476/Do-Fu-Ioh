import json

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

    def _create_and_join_match(self):
        self.client.login(username='host', password='123456')
        create_response = self.client.post('/api/match/create/', data='{}', content_type='application/json')
        room_code = create_response.json()['room_code']
        self.client.logout()

        self.client.login(username='guest', password='123456')
        self.client.post(f'/api/match/{room_code}/join/', data='{}', content_type='application/json')
        self.client.logout()
        return room_code

    def _host_summon_first_card(self, room_code):
        self.client.login(username='host', password='123456')
        summon_response = self.client.post(
            f'/api/match/{room_code}/summon/',
            data=json.dumps({'hand_index': 0, 'x': 0, 'y': 0}),
            content_type='application/json',
        )
        self.assertEqual(summon_response.status_code, 200)
        unit = summon_response.json()['match']['host']['units'][0]
        return unit

    def test_match_state_shape_is_board_oriented(self):
        self.client.login(username='host', password='123456')
        response = self.client.post('/api/match/create/', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 201)

        state = response.json()['match']
        self.assertEqual(state['board']['width'], 12)
        self.assertEqual(state['board']['height'], 15)
        self.assertIn('actions', state['turn'])
        self.assertIn('event_log', state)
        self.assertIn('discard', state)
        self.assertEqual(state['turn']['active_side'], 'host')

    def test_summon_validates_cell_and_per_turn_limit(self):
        room_code = self._create_and_join_match()

        self.client.login(username='host', password='123456')
        invalid_zone = self.client.post(
            f'/api/match/{room_code}/summon/',
            data=json.dumps({'hand_index': 0, 'x': 3, 'y': 8}),
            content_type='application/json',
        )
        self.assertEqual(invalid_zone.status_code, 400)

        ok_summon = self.client.post(
            f'/api/match/{room_code}/summon/',
            data=json.dumps({'hand_index': 0, 'x': 1, 'y': 1}),
            content_type='application/json',
        )
        self.assertEqual(ok_summon.status_code, 200)

        second_summon = self.client.post(
            f'/api/match/{room_code}/summon/',
            data=json.dumps({'hand_index': 0, 'x': 2, 'y': 1}),
            content_type='application/json',
        )
        self.assertEqual(second_summon.status_code, 400)
        self.assertIn('máximo permitido', second_summon.json()['message'])

    def test_move_cannot_exceed_pm(self):
        room_code = self._create_and_join_match()
        summoned_unit = self._host_summon_first_card(room_code)

        end_turn_host = self.client.post(f'/api/match/{room_code}/end-turn/', data='{}', content_type='application/json')
        self.assertEqual(end_turn_host.status_code, 200)
        self.client.logout()

        self.client.login(username='guest', password='123456')
        end_turn_guest = self.client.post(f'/api/match/{room_code}/end-turn/', data='{}', content_type='application/json')
        self.assertEqual(end_turn_guest.status_code, 200)
        self.client.logout()

        self.client.login(username='host', password='123456')
        too_far = self.client.post(
            f'/api/match/{room_code}/move/',
            data=json.dumps({'unit_id': summoned_unit['id'], 'to_x': 5, 'to_y': 0}),
            content_type='application/json',
        )
        self.assertEqual(too_far.status_code, 400)
        self.assertIn('más allá del PM', too_far.json()['message'])

    def test_attack_checks_range(self):
        room_code = self._create_and_join_match()

        self.client.login(username='host', password='123456')
        host_summon = self.client.post(
            f'/api/match/{room_code}/summon/',
            data=json.dumps({'hand_index': 0, 'x': 0, 'y': 0}),
            content_type='application/json',
        ).json()['match']['host']['units'][0]
        self.client.post(f'/api/match/{room_code}/end-turn/', data='{}', content_type='application/json')
        self.client.logout()

        self.client.login(username='guest', password='123456')
        guest_summon = self.client.post(
            f'/api/match/{room_code}/summon/',
            data=json.dumps({'hand_index': 0, 'x': 10, 'y': 14}),
            content_type='application/json',
        ).json()['match']['guest']['units'][0]
        self.client.post(f'/api/match/{room_code}/end-turn/', data='{}', content_type='application/json')
        self.client.logout()

        self.client.login(username='host', password='123456')
        out_of_range = self.client.post(
            f'/api/match/{room_code}/attack/',
            data=json.dumps({'attacker_id': host_summon['id'], 'target_id': guest_summon['id']}),
            content_type='application/json',
        )
        self.assertEqual(out_of_range.status_code, 400)
        self.assertIn('rango permitido', out_of_range.json()['message'])

    def test_draw_once_per_turn_and_state_persists(self):
        room_code = self._create_and_join_match()

        self.client.login(username='host', password='123456')
        first_draw = self.client.post(f'/api/match/{room_code}/draw/', data='{}', content_type='application/json')
        self.assertEqual(first_draw.status_code, 200)
        self.assertTrue(first_draw.json()['match']['turn']['actions']['draw_used'])

        second_draw = self.client.post(f'/api/match/{room_code}/draw/', data='{}', content_type='application/json')
        self.assertEqual(second_draw.status_code, 400)

        persisted = self.client.get(f'/api/match/{room_code}/')
        self.assertEqual(persisted.status_code, 200)
        self.assertTrue(persisted.json()['match']['turn']['actions']['draw_used'])

    def test_end_turn_alternates_active_player(self):
        room_code = self._create_and_join_match()

        self.client.login(username='host', password='123456')
        end_turn = self.client.post(f'/api/match/{room_code}/end-turn/', data='{}', content_type='application/json')
        self.assertEqual(end_turn.status_code, 200)
        self.assertEqual(end_turn.json()['match']['turn']['active_side'], 'guest')
