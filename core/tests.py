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
            data=json.dumps({'hand_index': 0, 'x': 5, 'y': 0}),
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
        self.assertEqual(state['board']['width'], 11)
        self.assertEqual(state['board']['height'], 11)
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
            data=json.dumps({'hand_index': 0, 'x': 4, 'y': 1}),
            content_type='application/json',
        )
        self.assertEqual(ok_summon.status_code, 200)

        second_summon = self.client.post(
            f'/api/match/{room_code}/summon/',
            data=json.dumps({'hand_index': 0, 'x': 5, 'y': 1}),
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
            data=json.dumps({'unit_id': summoned_unit['id'], 'to_x': 10, 'to_y': 0}),
            content_type='application/json',
        )
        self.assertEqual(too_far.status_code, 400)
        self.assertIn('más allá del PM', too_far.json()['message'])

    def test_attack_checks_range(self):
        room_code = self._create_and_join_match()

        self.client.login(username='host', password='123456')
        host_summon = self.client.post(
            f'/api/match/{room_code}/summon/',
            data=json.dumps({'hand_index': 0, 'x': 5, 'y': 0}),
            content_type='application/json',
        ).json()['match']['host']['units'][0]
        self.client.post(f'/api/match/{room_code}/end-turn/', data='{}', content_type='application/json')
        self.client.logout()

        self.client.login(username='guest', password='123456')
        guest_summon = self.client.post(
            f'/api/match/{room_code}/summon/',
            data=json.dumps({'hand_index': 0, 'x': 5, 'y': 10}),
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


class AnonymousAIMatchTests(TestCase):
    def setUp(self):
        for family in ['Píos', 'Escarahojas', 'Gelatinas', 'Kitsus']:
            for idx in range(3):
                MonsterCard.objects.create(
                    family=family,
                    name=f'{family} Carta {idx}',
                    slug=f'{family.lower()}-carta-{idx}'.replace('í', 'i'),
                    stage='base',
                    level_min=1,
                    level_max=2,
                    hp=5,
                    shell=1,
                    action_points=2,
                    movement_points=2,
                    description='test',
                )

    def test_guest_can_create_vs_ai_match_without_auth(self):
        response = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload['match']['mode'], 'vs_ai')
        self.assertEqual(payload['match']['viewer_side'], 'host')
        self.assertEqual(payload['match']['host']['username'], 'Invitado')

    def test_guest_can_play_turn_and_ai_responds(self):
        created = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json').json()
        room_code = created['room_code']
        center_x = created['match']['board']['width'] // 2

        summon = self.client.post(
            f'/api/match/{room_code}/action/',
            data=json.dumps({'action': 'summon', 'hand_index': 0, 'x': center_x, 'y': 0}),
            content_type='application/json',
        )
        self.assertEqual(summon.status_code, 200, summon.json())

        end_turn = self.client.post(
            f'/api/match/{room_code}/action/',
            data=json.dumps({'action': 'end_turn'}),
            content_type='application/json',
        )
        self.assertEqual(end_turn.status_code, 200)
        state = end_turn.json()['match']
        self.assertEqual(state['turn']['active_side'], 'host')
        self.assertTrue(any(event['event'].startswith('ai_') for event in state['event_log']))

    def test_anonymous_cannot_create_pvp_match(self):
        response = self.client.post('/api/match/create/', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 401)

    def test_vs_ai_bootstraps_cards_when_catalog_is_empty(self):
        MonsterCard.objects.all().delete()

        response = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 201)

        payload = response.json()
        self.assertGreater(MonsterCard.objects.count(), 0)
        self.assertGreater(len(payload['match']['host']['hand']), 0)


class AuthFlowTests(TestCase):
    def test_login_without_profile_does_not_raise_server_error(self):
        user = User.objects.create_user(username='sinperfil', password='123456')
        user.profile.delete()

        response = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'username': 'sinperfil', 'password': '123456'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['avatar_url'], '')
