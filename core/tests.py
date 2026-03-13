import json
import os
from unittest.mock import patch

from django.test import TestCase

from .models import MonsterCard
from .views import _sanitize_env_value, _schema_diagnostics


class SoloAIModeTests(TestCase):
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

    def test_create_vs_ai_without_auth(self):
        response = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload['match']['mode'], 'vs_ai')
        self.assertEqual(payload['match']['viewer_side'], 'host')
        self.assertEqual(payload['match']['host']['username'], 'Jugador')

    def test_turn_flow_and_ai_response(self):
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
        self.assertTrue(any(event['event'].startswith('ai_') for event in state['event_log']))

    def test_removed_features_return_gone(self):
        post_endpoints = [
            '/api/match/create/',
            '/api/auth/register/',
            '/api/auth/login/',
            '/api/auth/logout/',
            '/api/decks/',
        ]
        for endpoint in post_endpoints:
            response = self.client.post(endpoint, data='{}', content_type='application/json')
            self.assertEqual(response.status_code, 410)

        profile_response = self.client.get('/api/auth/profile/')
        self.assertEqual(profile_response.status_code, 410)

    def test_match_is_session_bound(self):
        created = self.client.post('/api/match/create-vs-ai/', data='{}', content_type='application/json').json()
        room_code = created['room_code']

        ok_response = self.client.get(f'/api/match/{room_code}/')
        self.assertEqual(ok_response.status_code, 200)

        other_client = self.client_class()
        blocked = other_client.get(f'/api/match/{room_code}/')
        self.assertEqual(blocked.status_code, 404)


class EnvironmentParsingTests(TestCase):
    def test_sanitize_env_value_removes_key_prefix(self):
        self.assertEqual(
            _sanitize_env_value('DATABASE_URL=postgresql://example', 'DATABASE_URL'),
            'postgresql://example',
        )

    def test_schema_diagnostics_warns_prefixed_database_url(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'DATABASE_URL=postgresql://example'}, clear=False):
            diagnostics = _schema_diagnostics()
        self.assertTrue(any('sin el prefijo DATABASE_URL=' in item for item in diagnostics))
