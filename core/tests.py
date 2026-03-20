import json

from django.middleware.csrf import _get_new_csrf_string
from django.test import Client, TestCase

from .models import MatchRecord, MonsterCard


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

    def test_move_rejects_destination_behind_occupied_cells(self):
        created = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json').json()
        room_code = created['room_code']
        center_x = created['match']['board']['width'] // 2
        playable_index = next(
            index for index, card in enumerate(created['match']['host']['hand']) if card['summon_cost'] <= 1
        )

        summon = self.client.post(
            f'/api/match/{room_code}/action/',
            data=json.dumps({'action': 'summon', 'hand_index': playable_index, 'x': center_x, 'y': 0}),
            content_type='application/json',
        )
        self.assertEqual(summon.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        unit = state['host']['units'][0]
        unit['pm_current'] = 3
        unit['card']['movement_points'] = 3
        state['host']['units'].extend([
            {
                'id': 'block-left',
                'owner': 'host',
                'x': center_x - 1,
                'y': 0,
                'card': unit['card'],
                'hp_current': 6,
                'shell_current': 1,
                'pa_current': 2,
                'pm_current': 0,
                'can_act': False,
                'can_move': False,
                'summoned_turn': 1,
            },
            {
                'id': 'block-right',
                'owner': 'host',
                'x': center_x + 1,
                'y': 0,
                'card': unit['card'],
                'hp_current': 6,
                'shell_current': 1,
                'pa_current': 2,
                'pm_current': 0,
                'can_act': False,
                'can_move': False,
                'summoned_turn': 1,
            },
            {
                'id': 'block-front',
                'owner': 'host',
                'x': center_x,
                'y': 1,
                'card': unit['card'],
                'hp_current': 6,
                'shell_current': 1,
                'pa_current': 2,
                'pm_current': 0,
                'can_act': False,
                'can_move': False,
                'summoned_turn': 1,
            },
        ])
        record.game_state = state
        record.save(update_fields=['game_state'])

        blocked_move = self.client.post(
            f'/api/match/{room_code}/action/',
            data=json.dumps({'action': 'move', 'unit_id': unit['id'], 'to_x': center_x, 'to_y': 2}),
            content_type='application/json',
        )

        self.assertEqual(blocked_move.status_code, 400)
        self.assertEqual(blocked_move.json()['message'], 'Movimiento fuera de rango.')

        record.refresh_from_db()
        moved_unit = record.game_state['host']['units'][0]
        self.assertEqual((moved_unit['x'], moved_unit['y']), (center_x, 0))

    def test_active_match_payload_exposes_only_reachable_destinations(self):
        created = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json').json()
        room_code = created['room_code']
        center_x = created['match']['board']['width'] // 2
        playable_index = next(
            index for index, card in enumerate(created['match']['host']['hand']) if card['summon_cost'] <= 1
        )

        summon = self.client.post(
            f'/api/match/{room_code}/action/',
            data=json.dumps({'action': 'summon', 'hand_index': playable_index, 'x': center_x, 'y': 0}),
            content_type='application/json',
        )
        self.assertEqual(summon.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        unit = state['host']['units'][0]
        unit['pm_current'] = 3
        state['host']['units'].append({
            'id': 'block-front',
            'owner': 'host',
            'x': center_x,
            'y': 1,
            'card': unit['card'],
            'hp_current': 6,
            'shell_current': 1,
            'pa_current': 2,
            'pm_current': 0,
            'can_act': False,
            'can_move': False,
            'summoned_turn': 1,
        })
        record.game_state = state
        record.save(update_fields=['game_state'])

        active = self.client.get(f'/api/match/{room_code}/')
        self.assertEqual(active.status_code, 200)
        host_unit = active.json()['match']['host']['units'][0]
        reachable_cells = {(cell['x'], cell['y']) for cell in host_unit['reachable_cells']}

        self.assertNotIn((center_x, 2), reachable_cells)
        self.assertIn((center_x - 1, 0), reachable_cells)
