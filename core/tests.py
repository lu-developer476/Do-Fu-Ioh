import json

from django.core.management import call_command
from django.middleware.csrf import _get_new_csrf_string
from django.test import Client, SimpleTestCase, TestCase

from django.contrib.auth.models import User

from .models import MatchRecord, MonsterCard
from .system_users import AI_USERNAME, SOLO_PLAYER_USERNAME, get_single_player_system_users
from .views import _ai_turn, _resolve_card_image, _serialize_card, _validate_match_state


class CardsCatalogSeedTests(TestCase):
    def test_cards_endpoint_does_not_seed_catalog_implicitly(self):
        MonsterCard.objects.all().delete()

        response = self.client.get('/api/cards/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['cards'], [])
        self.assertFalse(MonsterCard.objects.exists())

    def test_management_command_seeds_when_catalog_is_empty(self):
        MonsterCard.objects.all().delete()

        call_command('seed_cards_catalog')

        self.assertTrue(MonsterCard.objects.exists())

    def test_management_command_is_idempotent(self):
        MonsterCard.objects.all().delete()

        call_command('seed_cards_catalog')
        first_count = MonsterCard.objects.count()

        call_command('seed_cards_catalog')

        self.assertEqual(MonsterCard.objects.count(), first_count)


class UserProfileSignalTests(TestCase):
    def test_creates_profile_for_new_users(self):
        user = User.objects.create_user(username="signal-user", password="secret123")

        self.assertTrue(hasattr(user, "profile"))
        self.assertEqual(user.profile.user, user)


class SoloAIModeTests(TestCase):
    def setUp(self):
        for family in ["Pios", "Escarahojas", "Gelatinas", "Kitsus"]:
            for idx in range(3):
                MonsterCard.objects.create(
                    family=family,
                    name=f"{family} Carta {idx}",
                    slug=f"{family.lower()}-carta-{idx}",
                    stage="base" if idx == 0 else "fusion" if idx == 1 else "evolution",
                    level_min=1,
                    level_max=2,
                    hp=6,
                    shell=1,
                    action_points=2,
                    movement_points=2,
                    description="test",
                    image="public/images/pios/base/pio-albino.png",
                )

    def _create_match(self):
        response = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _summon_first_affordable_host_unit(self, room_code, match_payload, x=None, y=0):
        center_x = match_payload["match"]["board"]["width"] // 2
        summon_x = center_x if x is None else x
        playable_index = next(
            index
            for index, card in enumerate(match_payload["match"]["host"]["hand"])
            if card["summon_cost"] <= 1
        )
        response = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "summon",
                    "hand_index": playable_index,
                    "x": summon_x,
                    "y": y,
                }
            ),
            content_type="application/json",
        )
        return response, summon_x

    def test_single_player_uses_reserved_system_users_only_as_internal_actors(self):
        solo_user, ai_user = get_single_player_system_users()

        self.assertEqual(solo_user.username, SOLO_PLAYER_USERNAME)
        self.assertEqual(ai_user.username, AI_USERNAME)
        self.assertFalse(solo_user.is_active)
        self.assertFalse(ai_user.is_active)
        self.assertFalse(solo_user.has_usable_password())
        self.assertFalse(ai_user.has_usable_password())

        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        )
        self.assertEqual(created.status_code, 200)

        record = MatchRecord.objects.get(room_code=created.json()["room_code"])
        self.assertEqual(record.host.username, SOLO_PLAYER_USERNAME)
        self.assertEqual(record.guest.username, AI_USERNAME)
        self.assertEqual(User.objects.filter(username__in=[SOLO_PLAYER_USERNAME, AI_USERNAME]).count(), 2)

    def test_create_match_and_recover_from_session(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        )
        self.assertEqual(created.status_code, 200)
        payload = created.json()
        self.assertEqual(payload["match"]["mode"], "vs_ai")
        self.assertEqual(payload["match"]["turn"]["active_side"], "host")

        active = self.client.get("/api/match/active/")
        self.assertEqual(active.status_code, 200)
        self.assertEqual(active.json()["room_code"], payload["room_code"])

    def test_session_is_required_for_match_access(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]

        ok = self.client.get(f"/api/match/{room_code}/")
        self.assertEqual(ok.status_code, 200)

        other_client = self.client_class()
        denied = other_client.get(f"/api/match/{room_code}/")
        self.assertEqual(denied.status_code, 404)

    def test_turn_actions_work_without_user_login(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]
        center_x = created["match"]["board"]["width"] // 2
        hand = created["match"]["host"]["hand"]
        playable_index = next(
            index for index, card in enumerate(hand) if card["summon_cost"] <= 1
        )

        summon = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "summon",
                    "hand_index": playable_index,
                    "x": center_x,
                    "y": 0,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(summon.status_code, 200)

        end_turn = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps({"action": "end_turn"}),
            content_type="application/json",
        )
        self.assertEqual(end_turn.status_code, 200)
        state = end_turn.json()["match"]
        self.assertEqual(state["turn"]["active_side"], "host")
        self.assertTrue(any("Fin del turno" in item for item in state["log"]))

    def test_cards_expose_resolved_images_and_summon_cost(self):
        response = self.client.get("/api/cards/")
        self.assertEqual(response.status_code, 200)
        card = response.json()["cards"][0]
        self.assertTrue(card["image"].startswith("/static/"))
        self.assertIn(card["summon_cost"], {1, 3, 5})

    def test_index_bootstrap_sets_csrf_cookie_for_fetch_requests(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", client.cookies)

        csrf_token = client.cookies["csrftoken"].value
        created = client.post(
            "/api/match/create-vs-ai/",
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(created.status_code, 200)

    def test_match_actions_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        without_csrf = client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        )
        self.assertEqual(without_csrf.status_code, 403)

        csrf_token = _get_new_csrf_string()
        client.cookies["csrftoken"] = csrf_token
        with_csrf = client.post(
            "/api/match/create-vs-ai/",
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(with_csrf.status_code, 200)

    def test_move_rejects_destination_behind_occupied_cells(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]
        center_x = created["match"]["board"]["width"] // 2
        playable_index = next(
            index
            for index, card in enumerate(created["match"]["host"]["hand"])
            if card["summon_cost"] <= 1
        )

        summon = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "summon",
                    "hand_index": playable_index,
                    "x": center_x,
                    "y": 0,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(summon.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        unit = state["host"]["units"][0]
        unit["pm_current"] = 3
        unit["card"]["movement_points"] = 3
        state["host"]["units"].extend(
            [
                {
                    "id": "block-left",
                    "owner": "host",
                    "x": center_x - 1,
                    "y": 0,
                    "card": unit["card"],
                    "hp_current": 6,
                    "shell_current": 1,
                    "pa_current": 2,
                    "pm_current": 0,
                    "can_act": False,
                    "can_move": False,
                    "summoned_turn": 1,
                },
                {
                    "id": "block-right",
                    "owner": "host",
                    "x": center_x + 1,
                    "y": 0,
                    "card": unit["card"],
                    "hp_current": 6,
                    "shell_current": 1,
                    "pa_current": 2,
                    "pm_current": 0,
                    "can_act": False,
                    "can_move": False,
                    "summoned_turn": 1,
                },
                {
                    "id": "block-front",
                    "owner": "host",
                    "x": center_x,
                    "y": 1,
                    "card": unit["card"],
                    "hp_current": 6,
                    "shell_current": 1,
                    "pa_current": 2,
                    "pm_current": 0,
                    "can_act": False,
                    "can_move": False,
                    "summoned_turn": 1,
                },
            ]
        )
        record.game_state = state
        record.save(update_fields=["game_state"])

        blocked_move = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {"action": "move", "unit_id": unit["id"], "to_x": center_x, "to_y": 2}
            ),
            content_type="application/json",
        )

        self.assertEqual(blocked_move.status_code, 400)
        self.assertEqual(blocked_move.json()["message"], "Movimiento fuera de rango.")

        record.refresh_from_db()
        moved_unit = record.game_state["host"]["units"][0]
        self.assertEqual((moved_unit["x"], moved_unit["y"]), (center_x, 0))

    def test_active_match_payload_exposes_only_reachable_destinations(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]
        center_x = created["match"]["board"]["width"] // 2
        playable_index = next(
            index
            for index, card in enumerate(created["match"]["host"]["hand"])
            if card["summon_cost"] <= 1
        )

        summon = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "summon",
                    "hand_index": playable_index,
                    "x": center_x,
                    "y": 0,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(summon.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        unit = state["host"]["units"][0]
        unit["pm_current"] = 3
        state["host"]["units"].append(
            {
                "id": "block-front",
                "owner": "host",
                "x": center_x,
                "y": 1,
                "card": unit["card"],
                "hp_current": 6,
                "shell_current": 1,
                "pa_current": 2,
                "pm_current": 0,
                "can_act": False,
                "can_move": False,
                "summoned_turn": 1,
            }
        )
        record.game_state = state
        record.save(update_fields=["game_state"])

        active = self.client.get(f"/api/match/{room_code}/")
        self.assertEqual(active.status_code, 200)
        host_unit = active.json()["match"]["host"]["units"][0]
        reachable_cells = {
            (cell["x"], cell["y"]) for cell in host_unit["reachable_cells"]
        }

        self.assertNotIn((center_x, 2), reachable_cells)
        self.assertIn((center_x - 1, 0), reachable_cells)

    def test_game_does_not_end_if_enemy_has_cards_left_to_play(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]
        center_x = created["match"]["board"]["width"] // 2
        playable_index = next(
            index
            for index, card in enumerate(created["match"]["host"]["hand"])
            if card["summon_cost"] <= 1
        )

        summon = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "summon",
                    "hand_index": playable_index,
                    "x": center_x,
                    "y": 0,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(summon.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        host_unit = state["host"]["units"][0]
        host_unit["x"] = center_x
        host_unit["y"] = state["board"]["height"] - 2
        host_unit["pa_current"] = 3
        host_unit["can_act"] = True
        state["guest"]["units"] = [
            {
                "id": "guest-frontliner",
                "owner": "guest",
                "x": center_x,
                "y": state["board"]["height"] - 1,
                "card": host_unit["card"],
                "hp_current": 1,
                "shell_current": 0,
                "pa_current": 0,
                "pm_current": 0,
                "can_act": False,
                "can_move": False,
                "summoned_turn": 1,
            }
        ]
        state["guest"]["hand"] = [state["guest"]["hand"][0]]
        state["guest"]["library"] = []
        record.game_state = state
        record.save(update_fields=["game_state"])

        attack = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "attack",
                    "attacker_id": host_unit["id"],
                    "target_id": "guest-frontliner",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(attack.status_code, 200)
        payload = attack.json()
        self.assertIsNone(payload["match"]["winner"])
        self.assertEqual(payload["status"], "active")

    def test_game_ends_when_ai_removes_last_host_resource(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        state["turn"]["active_side"] = "host"
        state["host"]["hand"] = []
        state["host"]["library"] = []
        state["host"]["units"] = []
        state["guest"]["hand"] = []
        state["guest"]["library"] = []
        state["guest"]["units"] = [
            {
                "id": "guest-survivor",
                "owner": "guest",
                "x": state["board"]["width"] // 2,
                "y": state["board"]["height"] - 2,
                "card": {
                    "id": 999,
                    "name": "Test Guest",
                    "slug": "test-guest",
                    "family": "Tests",
                    "stage": "base",
                    "level_min": 1,
                    "level_max": 1,
                    "hp": 6,
                    "shell": 0,
                    "action_points": 2,
                    "movement_points": 2,
                    "description": "test",
                    "image": "",
                    "summon_cost": 1,
                },
                "hp_current": 6,
                "shell_current": 0,
                "pa_current": 2,
                "pm_current": 2,
                "can_act": True,
                "can_move": True,
                "summoned_turn": 1,
            }
        ]
        record.game_state = state
        record.save(update_fields=["game_state"])

        end_turn = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps({"action": "end_turn"}),
            content_type="application/json",
        )

        self.assertEqual(end_turn.status_code, 200)
        payload = end_turn.json()
        self.assertEqual(payload["match"]["winner"], "guest")
        self.assertEqual(payload["status"], "finished")

    def test_summon_rejects_cells_outside_deployment_zone(self):
        created = self._create_match()
        room_code = created["room_code"]

        response, center_x = self._summon_first_affordable_host_unit(
            room_code, created, y=3
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "Sólo podés invocar en tu zona azul.")

        record = MatchRecord.objects.get(room_code=room_code)
        self.assertEqual(record.game_state["host"]["units"], [])
        self.assertEqual(record.game_state["host"]["energy"], 1)
        self.assertFalse(any(str((center_x, 3)) in item for item in record.game_state["log"]))

    def test_summon_rejects_when_energy_is_insufficient(self):
        created = self._create_match()
        room_code = created["room_code"]
        center_x = created["match"]["board"]["width"] // 2
        costly_index = next(
            index
            for index, card in enumerate(created["match"]["host"]["hand"])
            if card["summon_cost"] > created["match"]["host"]["energy"]
        )

        response = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {"action": "summon", "hand_index": costly_index, "x": center_x, "y": 0}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "No alcanza la energía para invocar.")

        record = MatchRecord.objects.get(room_code=room_code)
        self.assertEqual(record.game_state["host"]["units"], [])
        self.assertEqual(record.game_state["host"]["energy"], 1)
        self.assertEqual(len(record.game_state["host"]["hand"]), len(created["match"]["host"]["hand"]))

    def test_move_rejects_destination_outside_board(self):
        created = self._create_match()
        room_code = created["room_code"]
        summon, center_x = self._summon_first_affordable_host_unit(room_code, created)
        self.assertEqual(summon.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        unit = state["host"]["units"][0]
        unit["pm_current"] = 3
        unit["can_move"] = True
        record.game_state = state
        record.save(update_fields=["game_state"])

        response = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {"action": "move", "unit_id": unit["id"], "to_x": center_x, "to_y": -1}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "Destino inválido.")

        record.refresh_from_db()
        moved_unit = record.game_state["host"]["units"][0]
        self.assertEqual((moved_unit["x"], moved_unit["y"]), (center_x, 0))

    def test_move_rejects_occupied_destination(self):
        created = self._create_match()
        room_code = created["room_code"]
        summon, center_x = self._summon_first_affordable_host_unit(room_code, created)
        self.assertEqual(summon.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        unit = state["host"]["units"][0]
        unit["pm_current"] = 3
        unit["can_move"] = True
        state["host"]["units"].append(
            {
                "id": "friendly-blocker",
                "owner": "host",
                "x": center_x + 1,
                "y": 0,
                "card": unit["card"],
                "hp_current": 6,
                "shell_current": 1,
                "pa_current": 0,
                "pm_current": 0,
                "can_act": False,
                "can_move": False,
                "summoned_turn": 1,
            }
        )
        record.game_state = state
        record.save(update_fields=["game_state"])

        response = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "move",
                    "unit_id": unit["id"],
                    "to_x": center_x + 1,
                    "to_y": 0,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "Movimiento fuera de rango.")

        record.refresh_from_db()
        moved_unit = record.game_state["host"]["units"][0]
        self.assertEqual((moved_unit["x"], moved_unit["y"]), (center_x, 0))

    def test_attack_rejects_target_out_of_range(self):
        created = self._create_match()
        room_code = created["room_code"]
        summon, center_x = self._summon_first_affordable_host_unit(room_code, created)
        self.assertEqual(summon.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        attacker = state["host"]["units"][0]
        attacker["pa_current"] = 2
        attacker["can_act"] = True
        state["guest"]["units"] = [
            {
                "id": "far-target",
                "owner": "guest",
                "x": center_x,
                "y": 4,
                "card": attacker["card"],
                "hp_current": 6,
                "shell_current": 1,
                "pa_current": 0,
                "pm_current": 0,
                "can_act": False,
                "can_move": False,
                "summoned_turn": 1,
            }
        ]
        record.game_state = state
        record.save(update_fields=["game_state"])

        response = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "attack",
                    "attacker_id": attacker["id"],
                    "target_id": "far-target",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "Objetivo fuera de rango o sin PA.")

        record.refresh_from_db()
        self.assertEqual(record.game_state["guest"]["units"][0]["hp_current"], 6)

    def test_match_from_other_session_remains_inaccessible_after_actions(self):
        created = self._create_match()
        room_code = created["room_code"]
        summon, _ = self._summon_first_affordable_host_unit(room_code, created)
        self.assertEqual(summon.status_code, 200)

        other_client = self.client_class()
        direct = other_client.get(f"/api/match/{room_code}/")
        active = other_client.get("/api/match/active/")

        self.assertEqual(direct.status_code, 404)
        self.assertEqual(direct.json()["message"], "Partida no disponible para esta sesión.")
        self.assertEqual(active.status_code, 200)
        self.assertIsNone(active.json()["room_code"])
        self.assertIsNone(active.json()["match"])

    def test_game_ends_correctly_when_host_removes_last_guest_resource(self):
        created = self._create_match()
        room_code = created["room_code"]
        summon, center_x = self._summon_first_affordable_host_unit(room_code, created)
        self.assertEqual(summon.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        attacker = state["host"]["units"][0]
        attacker["x"] = center_x
        attacker["y"] = state["board"]["height"] - 2
        attacker["pa_current"] = 2
        attacker["can_act"] = True
        state["guest"]["hand"] = []
        state["guest"]["library"] = []
        state["guest"]["units"] = [
            {
                "id": "guest-last-unit",
                "owner": "guest",
                "x": center_x,
                "y": state["board"]["height"] - 1,
                "card": attacker["card"],
                "hp_current": 1,
                "shell_current": 0,
                "pa_current": 0,
                "pm_current": 0,
                "can_act": False,
                "can_move": False,
                "summoned_turn": 1,
            }
        ]
        record.game_state = state
        record.save(update_fields=["game_state"])

        response = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "attack",
                    "attacker_id": attacker["id"],
                    "target_id": "guest-last-unit",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["match"]["winner"], "host")
        self.assertEqual(payload["status"], "finished")
        self.assertEqual(payload["match"]["guest"]["units"], [])
        self.assertTrue(any("fue derrotado" in item for item in payload["match"]["log"]))

    def test_state_persists_after_turn_actions(self):
        created = self._create_match()
        room_code = created["room_code"]
        summon, center_x = self._summon_first_affordable_host_unit(room_code, created)
        self.assertEqual(summon.status_code, 200)
        summon_payload = summon.json()
        host_unit = summon_payload["match"]["host"]["units"][0]

        move = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps(
                {
                    "action": "move",
                    "unit_id": host_unit["id"],
                    "to_x": center_x + 1,
                    "to_y": 0,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(move.status_code, 200)

        end_turn = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps({"action": "end_turn"}),
            content_type="application/json",
        )
        self.assertEqual(end_turn.status_code, 200)

        record = MatchRecord.objects.get(room_code=room_code)
        persisted_unit = next(
            unit for unit in record.game_state["host"]["units"] if unit["id"] == host_unit["id"]
        )
        self.assertEqual((persisted_unit["x"], persisted_unit["y"]), (center_x + 1, 0))
        self.assertEqual(record.game_state["turn"]["active_side"], "host")
        self.assertEqual(record.status, "active")
        self.assertTrue(any("host movió" in item for item in record.game_state["log"]))
        self.assertTrue(any("Fin del turno de host." == item for item in record.game_state["log"]))

    def test_create_match_accepts_ai_difficulty_levels(self):
        created = self.client.post(
            "/api/match/create-vs-ai/",
            data=json.dumps({"difficulty": "extremo"}),
            content_type="application/json",
        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["match"]["ai_difficulty"], "extremo")

    def test_ai_attacks_before_ending_turn_when_target_is_in_range(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        state["turn"]["active_side"] = "guest"
        state["turn"]["number"] = 2
        state["ai_difficulty"] = "normal"
        state["host"]["hand"] = []
        state["host"]["library"] = []
        state["guest"]["hand"] = []
        state["guest"]["library"] = []
        state["host"]["hand_count"] = 0
        state["host"]["library_count"] = 0
        state["guest"]["hand_count"] = 0
        state["guest"]["library_count"] = 0
        card = {
            "id": 501,
            "name": "Host Dummy",
            "slug": "host-dummy",
            "family": "Tests",
            "stage": "base",
            "level_min": 1,
            "level_max": 1,
            "hp": 6,
            "shell": 0,
            "action_points": 2,
            "movement_points": 2,
            "description": "test",
            "image": "",
            "summon_cost": 1,
        }
        state["host"]["units"] = [
            {
                "id": "host-front",
                "owner": "host",
                "x": 5,
                "y": 3,
                "card": card,
                "hp_current": 6,
                "shell_current": 0,
                "pa_current": 2,
                "pm_current": 2,
                "can_act": True,
                "can_move": True,
                "summoned_turn": 1,
            }
        ]
        state["guest"]["units"] = [
            {
                "id": "guest-front",
                "owner": "guest",
                "x": 5,
                "y": 5,
                "card": {**card, "id": 502, "name": "Guest Dummy"},
                "hp_current": 6,
                "shell_current": 0,
                "pa_current": 2,
                "pm_current": 2,
                "can_act": True,
                "can_move": True,
                "summoned_turn": 1,
            }
        ]
        record.game_state = state
        record.save(update_fields=["game_state"])

        _ai_turn(state)

        payload = state
        self.assertIn(payload["turn"]["active_side"], {"guest", "host"})
        self.assertTrue(payload["winner"] in {None, "guest"})
        host_units = payload["host"]["units"]
        if host_units:
            self.assertLess(host_units[0]["hp_current"], 6)
        else:
            self.assertEqual(payload["winner"], "guest")
        self.assertTrue(any("guest atacó" in item for item in payload["log"]))

    def test_ai_moves_towards_enemy_instead_of_wasting_turn(self):
        created = self.client.post(
            "/api/match/create-vs-ai/",
            data=json.dumps({"difficulty": "extremo"}),
            content_type="application/json",
        ).json()
        room_code = created["room_code"]

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        state["turn"]["active_side"] = "guest"
        state["turn"]["number"] = 2
        state["host"]["hand"] = []
        state["host"]["library"] = []
        state["guest"]["hand"] = []
        state["guest"]["library"] = []
        state["host"]["hand_count"] = 0
        state["host"]["library_count"] = 0
        state["guest"]["hand_count"] = 0
        state["guest"]["library_count"] = 0
        card = {
            "id": 601,
            "name": "Mover",
            "slug": "mover",
            "family": "Tests",
            "stage": "base",
            "level_min": 1,
            "level_max": 1,
            "hp": 6,
            "shell": 0,
            "action_points": 2,
            "movement_points": 2,
            "description": "test",
            "image": "",
            "summon_cost": 1,
        }
        state["host"]["units"] = [
            {
                "id": "host-far",
                "owner": "host",
                "x": 5,
                "y": 0,
                "card": card,
                "hp_current": 6,
                "shell_current": 0,
                "pa_current": 2,
                "pm_current": 2,
                "can_act": True,
                "can_move": True,
                "summoned_turn": 1,
            }
        ]
        state["guest"]["units"] = [
            {
                "id": "guest-mover",
                "owner": "guest",
                "x": 5,
                "y": 8,
                "card": {**card, "id": 602, "name": "Guest Mover"},
                "hp_current": 6,
                "shell_current": 0,
                "pa_current": 2,
                "pm_current": 2,
                "can_act": True,
                "can_move": True,
                "summoned_turn": 1,
            }
        ]
        record.game_state = state
        record.save(update_fields=["game_state"])

        _ai_turn(state)

        payload = state
        moved_guest = payload["guest"]["units"][0]
        self.assertLess(moved_guest["y"], 8)
        self.assertTrue(any("guest movió" in item for item in payload["log"]))

    def test_match_action_returns_clear_json_for_corrupt_state(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        del state["turn"]["active_side"]
        record.game_state = state
        record.save(update_fields=["game_state"])

        response = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps({"action": "end_turn"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["message"],
            "Estado de partida inválido: turn.active_side debe ser 'host' o 'guest'.",
        )

    def test_get_match_returns_clear_json_for_partial_state(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]

        record = MatchRecord.objects.get(room_code=room_code)
        state = record.game_state
        state["host"] = {"side": "host"}
        record.game_state = state
        record.save(update_fields=["game_state"])

        response = self.client.get(f"/api/match/{room_code}/")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["message"],
            "Estado de partida inválido: host.energy debe ser un entero mayor o igual a 0.",
        )

    def test_match_action_rejects_unexpected_action_payload_types(self):
        created = self.client.post(
            "/api/match/create-vs-ai/", data="{}", content_type="application/json"
        ).json()
        room_code = created["room_code"]

        response = self.client.post(
            f"/api/match/{room_code}/action/",
            data=json.dumps({"action": "attack", "attacker_id": ["bad"], "target_id": 1}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["message"],
            "El campo 'attacker_id' debe ser un texto no vacío.",
        )


class AIBehaviorUnitTests(SimpleTestCase):
    def _card(self, *, card_id=1, name="Carta Test", stage="base", image=""):
        return {
            "id": card_id,
            "name": name,
            "slug": name.lower().replace(" ", "-"),
            "family": "Tests",
            "stage": stage,
            "level_min": 1,
            "level_max": 1,
            "hp": 6,
            "shell": 0,
            "action_points": 2,
            "movement_points": 2,
            "description": "test",
            "image": image,
            "summon_cost": 1 if stage == "base" else 3 if stage == "fusion" else 5,
        }

    def _unit(self, *, unit_id, owner, x, y, card=None):
        card = card or self._card()
        return {
            "id": unit_id,
            "owner": owner,
            "x": x,
            "y": y,
            "card": card,
            "hp_current": card["hp"],
            "shell_current": card["shell"],
            "pa_current": card["action_points"],
            "pm_current": card["movement_points"],
            "can_act": True,
            "can_move": True,
            "summoned_turn": 1,
        }

    def _state(self):
        return {
            "mode": "vs_ai",
            "ai_difficulty": "normal",
            "board": {"width": 11, "height": 11},
            "turn": {"number": 2, "active_side": "guest"},
            "host": {
                "side": "host",
                "energy": 1,
                "max_energy": 1,
                "hand": [],
                "library": [],
                "library_count": 0,
                "hand_count": 0,
                "units": [],
                "summons_this_turn": 0,
            },
            "guest": {
                "side": "guest",
                "energy": 1,
                "max_energy": 1,
                "hand": [],
                "library": [],
                "library_count": 0,
                "hand_count": 0,
                "units": [],
                "summons_this_turn": 0,
            },
            "winner": None,
            "log": [],
        }

    def test_ai_summons_when_it_has_energy_and_cards_in_hand(self):
        state = self._state()
        state["host"]["units"] = [self._unit(unit_id="host-front", owner="host", x=5, y=0)]
        state["guest"]["hand"] = [self._card(card_id=2, name="Invocable")]
        state["guest"]["hand_count"] = 1

        _ai_turn(state)

        self.assertEqual(len(state["guest"]["units"]), 1)
        self.assertEqual(state["guest"]["energy"], 0)
        self.assertEqual(state["guest"]["hand_count"], 0)
        self.assertTrue(any("guest invocó Invocable" in item for item in state["log"]))

    def test_ai_attacks_when_target_is_in_range(self):
        state = self._state()
        state["host"]["units"] = [self._unit(unit_id="host-front", owner="host", x=5, y=3)]
        state["guest"]["units"] = [
            self._unit(unit_id="guest-front", owner="guest", x=5, y=5, card=self._card(card_id=2, name="Atacante"))
        ]

        _ai_turn(state)

        host_units = state["host"]["units"]
        if host_units:
            self.assertLess(host_units[0]["hp_current"], 6)
        else:
            self.assertEqual(state["winner"], "guest")
        self.assertTrue(any("guest atacó con Atacante" in item for item in state["log"]))

    def test_ai_ends_turn_and_returns_control_to_host(self):
        state = self._state()

        _ai_turn(state)

        self.assertEqual(state["turn"]["active_side"], "host")
        self.assertEqual(state["turn"]["number"], 3)
        self.assertTrue(any(item == "Fin del turno de guest." for item in state["log"]))

    def test_ai_turn_keeps_match_state_valid(self):
        state = self._state()
        state["host"]["units"] = [self._unit(unit_id="host-front", owner="host", x=5, y=1)]
        state["guest"]["hand"] = [self._card(card_id=2, name="Invocable")]
        state["guest"]["hand_count"] = 1

        _ai_turn(state)

        self.assertIsNone(_validate_match_state(state))


class ViewCardSerializationHelpersTests(SimpleTestCase):
    def test_resolve_card_image_supports_relative_absolute_remote_public_and_empty_paths(self):
        self.assertEqual(_resolve_card_image("images/card.png"), "/static/images/card.png")
        self.assertEqual(_resolve_card_image("/images/card.png"), "/images/card.png")
        self.assertEqual(_resolve_card_image("http://cdn.example.com/card.png"), "http://cdn.example.com/card.png")
        self.assertEqual(_resolve_card_image("https://cdn.example.com/card.png"), "https://cdn.example.com/card.png")
        self.assertEqual(_resolve_card_image("public/images/card.png"), "/static/images/card.png")
        self.assertEqual(_resolve_card_image(""), "")

    def test_serialize_card_resolves_supported_image_variants(self):
        variants = [
            ("images/card.png", "/static/images/card.png"),
            ("/images/card.png", "/images/card.png"),
            ("http://cdn.example.com/card.png", "http://cdn.example.com/card.png"),
            ("https://cdn.example.com/card.png", "https://cdn.example.com/card.png"),
            ("public/images/card.png", "/static/images/card.png"),
            ("", ""),
        ]

        for index, (raw_image, expected_image) in enumerate(variants, start=1):
            with self.subTest(raw_image=raw_image):
                card = MonsterCard(
                    id=index,
                    family="Tests",
                    name=f"Carta {index}",
                    slug=f"carta-{index}",
                    stage="base",
                    level_min=1,
                    level_max=1,
                    hp=6,
                    shell=1,
                    action_points=2,
                    movement_points=2,
                    description="test",
                    image=raw_image,
                )

                payload = _serialize_card(card)

                self.assertEqual(payload["image"], expected_image)
                self.assertEqual(payload["summon_cost"], 1)
                self.assertEqual(payload["name"], card.name)
