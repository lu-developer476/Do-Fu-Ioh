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

    def test_escarahoja_spells_match_reference_lists(self):
        cards = {card['name']: card for card in load_cards_seed_data()}

        expected_base_spells = [
            'Escarainvoc',
            'Escarafuerza',
            'Dispersión Elemental',
            'Espíritu Elemental',
            'Fusión Escarahoja',
        ]
        base_names = [
            'Escarahoja anaranjada',
            'Escarahoja limonada',
            'Escarahoja sonrosada',
            'Escarahoja tostada',
            'Escarahoja violeta',
        ]
        for name in base_names:
            with self.subTest(card=name):
                card = cards[name]
                self.assertEqual(card['stage'], 'base')
                self.assertEqual(card['family'], 'Escarahojas')
                self.assertEqual([spell['name'] for spell in card['spells']], expected_base_spells)
                self.assertEqual(len(card['spells']), 5)
                self.assertEqual(
                    card['spells'][-1]['effect'],
                    'Sólo aplicable según lo descripto en los textos de las Escarahojas combinadas.',
                )

        expected_fusion_spells = [
            'Inmovilización',
            'Escarafuerza',
            'Elemental Dispersión',
            'Desaparición en Grupo',
            'Evolución',
        ]
        fusion_names = [
            'Escarahoja duocromada',
            'Escarahoja mecanizada',
            'Escarahoja tricolor',
            'Escarahoja variopinta',
        ]
        for name in fusion_names:
            with self.subTest(card=name):
                card = cards[name]
                self.assertEqual(card['stage'], 'fusion')
                self.assertEqual(card['family'], 'Escarahojas')
                self.assertEqual([spell['name'] for spell in card['spells']], expected_fusion_spells)
                self.assertEqual(len(card['spells']), 5)
                self.assertEqual(
                    card['spells'][-1]['effect'],
                    'El hechizo Evolución sólo lo puede utilizar 1 sola Escarahoja fusionada en el campo, '
                    'haya o no más Escarahojas fusionadas en combate.',
                )

        bronze = cards['Escarasubjefe Bronce']
        self.assertEqual(bronze['family'], 'Escarahojas')
        self.assertEqual(
            [spell['name'] for spell in bronze['spells']],
            ['Liberación', 'Cura Afrodisíaca', 'Picota', 'Humo Calcinador'],
        )
        self.assertEqual(len(bronze['spells']), 4)
        self.assertNotIn('Escarajefe Dorado', cards)


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
                self.assertEqual(card['hp_min'], hp)
                self.assertEqual(card['hp_max'], hp)

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


    def test_kitsu_descriptions_match_reference_texts(self):
        cards = {card['name']: card for card in load_cards_seed_data()}

        expected = {
            'Kitsu amatista': 'Espíritu kitsune de tonalidades violetas vinculado a las energías arcanas de Pandala.',
            'Kitsu anaranjado': 'Variante ardiente de los Kitsus cuya energía recuerda a las brasas de un fuego controlado.',
            'Kitsu carmine': 'Espíritu kitsu de tonalidad rojiza profunda asociado con la intensidad del Wakfu.',
            'Kitsu androide': 'Kitsu artificial reforzado con piezas tecnomágicas. Su núcleo mecánico estabiliza el Wakfu y convierte sus movimientos en patrones precisos y calculados.',
            'Kitsu dākuburakku': 'Kitsu oscuro que canaliza energías sombrías del Mundo de los Doce.',
            'Kitsu junsuina hikari': 'Manifestación espiritual del kitsu ligada a la pureza y la luz.',
            'Kitsu magenta': 'Espíritu kitsune de energía vibrante, errática y caótica. Su coloración intensa delata una afinidad con corrientes mágicas difíciles de controlar.',
            'Kitsu midori no mizu': 'Rara manifestación kitsune de la energía del agua como un manantial cargado de vida. Su presencia sugiere equilibrio entre fluidez y naturaleza, reflejando tonalidades esmeraldas.',
            'Kitsu mizu': 'Variante acuática inspirada en los antiguos Kitsus de Pandala. Su pelaje azul concentra una energía fluida, fría y constante, propia de los espíritus del agua.',
            'Kitsu silvestre': 'Forma más salvaje y agresiva del linaje que habita zonas naturales. Conserva el misticismo de Pandala, pero con un instinto más salvaje y territorial.',
            'Kitsu nishiki': 'Fusión espiritual entre Kitsu Mizu y Kitsu Midori no Mizu. Su pelaje de 2 colores recuerda a los koi ornamentales y refleja una armonía acuática poco frecuente.',
            'Kitsu penta': 'Manifestación extremadamente inestable surgida de la unión de cinco energías kitsu. Su energía es enorme, pero también inestable, como si varias voluntades convivieran en un mismo cuerpo.',
            'Kitsu yin yang': 'Fusión nacida del equilibrio entre la oscuridad del Kitsu dākuburakku y la pureza del Kitsu junsuina hikari. En él conviven dos corrientes opuestas de una misma esencia.',
            'Kitsu silvestre evolucionado': 'Evolución base del Kitsu silvestre. Al madurar, su vínculo con Pandala se refuerza y su instinto cazador se vuelve más preciso y dominante.',
            'Kitsu kumiawase': 'Evolución base del Kitsu amatista y magenta que representa la armonía entre 2 energías complementarias. Su nombre refleja la unión en una forma más estable y poderosa.',
            'Kitsu nishiki evolucionado': 'Evolución de la fusión Kitsu nishiki. Su pelaje gana brillo ceremonial y su cuerpo canaliza con más estabilidad las corrientes espirituales del agua.',
            'Kitsu penta evolucionado': 'Evolución de la fusión Kitsu penta. La enorme mezcla de energías deja de ser caótica y se transforma en una presencia majestuosa y peligrosa.',
            'Kitsu yin yang evolucionado': 'Evolución de la fusión Kitsu yin yang. Su cuerpo domina mejor la tensión entre luz y sombra, convirtiendo ese equilibrio en una fuerza propia.',
        }

        for name, description in expected.items():
            with self.subTest(card=name):
                self.assertEqual(cards[name]['description'], description)

    def test_kitsu_reference_spells_are_defined(self):
        cards = {card['name']: card for card in serialized_cards_seed_data()}
        kitsus = [card for card in cards.values() if card['family'] == 'Kitsus']

        for card in kitsus:
            spell_suffix = card['name'].removeprefix('Kitsu ')

            with self.subTest(card=card['name']):
                self.assertEqual(
                    [spell['name'] for spell in card['spells']],
                    [
                        f'Kitsnición {spell_suffix}',
                        f'Ilusión espectral {spell_suffix}',
                        f'Argucia del Kitsu {spell_suffix}',
                    ] + (['Evolución'] if card['stage'] == 'fusion' else ['Fusión Kitsu'] if card['stage'] == 'base' and card['name'] != 'Kitsu silvestre' else []),
                )
                self.assertEqual(len(card['spells']), 4 if (card['stage'] == 'fusion' or (card['stage'] == 'base' and card['name'] != 'Kitsu silvestre')) else 3)
                if card['stage'] == 'fusion':
                    self.assertIn('Kitsu fusionado', card['spells'][3]['effect'])
                if card['stage'] == 'base' and card['name'] != 'Kitsu silvestre':
                    self.assertIn('Kitsus compatibles', card['spells'][3]['effect'])
                for spell in card['spells']:
                    self.assertIn('cost', spell)
                    self.assertIn('range', spell)


class PioCatalogDataTests(SimpleTestCase):
    def test_pio_otonial_includes_evolution_spell(self):
        cards = {card['name']: card for card in serialized_cards_seed_data()}

        card = cards['Pío otoñal']
        self.assertEqual(card['stage'], 'fusion')
        self.assertEqual(
            [spell['name'] for spell in card['spells']],
            [
                'Picoteo otoñal',
                'Plumaje otoñal',
                'Evolución',
            ],
        )
        self.assertIn('Pío fusionado', card['spells'][2]['effect'])

    def test_pio_combinado_does_not_evolve_to_pioloro(self):
        cards = {card['name']: card for card in serialized_cards_seed_data()}

        card = cards['Pío combinado']
        self.assertEqual(card['stage'], 'fusion')
        self.assertEqual(
            [spell['name'] for spell in card['spells']],
            [
                'Picoteo combinado',
                'Plumaje combinado',
            ],
        )

    def test_pio_base_components_include_fusion_spell(self):
        cards = {card['name']: card for card in serialized_cards_seed_data()}

        for name in ['Pío albino', 'Pío negruzco', 'Pío anaranjado', 'Pío castaño', 'Pío cyborg']:
            with self.subTest(card=name):
                self.assertEqual(cards[name]['spells'][-1]['name'], 'Fusión Pío')
                self.assertEqual(cards[name]['spells'][-1]['damage_min'], 0)
                self.assertEqual(cards[name]['spells'][-1]['damage_max'], 0)
                self.assertIn('Pío compatible', cards[name]['spells'][-1]['effect'])

    def test_new_cyborg_base_monsters_are_available(self):
        cards = {card['name']: card for card in serialized_cards_seed_data()}

        expected = {
            'Pío cyborg': ('Píos', 'public/images/pios/base/pio-cyborg.png', 85, 105, 5, 5),
            'Kitsu androide': ('Kitsus', 'public/images/kitsus/base/kitsu-androide.png', 1500, 300, 9, 6),
        }

        for name, (family, image, hp, shell, action_points, movement_points) in expected.items():
            with self.subTest(card=name):
                card = cards[name]
                self.assertEqual(card['family'], family)
                self.assertEqual(card['stage'], 'base')
                self.assertEqual(card['image'], image.replace('public/', '/static/'))
                self.assertEqual(card['hp'], hp)
                self.assertEqual(card['shell'], shell)
                self.assertEqual(card['action_points'], action_points)
                self.assertEqual(card['movement_points'], movement_points)


class GelatinaCatalogDataTests(SimpleTestCase):
    def test_common_gelatinas_use_color_spells(self):
        cards = {card['name']: card for card in serialized_cards_seed_data()}

        expected_colors = {
            'Gelatina de durazno': 'durazno',
            'Gelatina de frambuesa': 'frambuesa',
            'Gelatina lactosada': 'descalcificado',
            'Gelatina moka': 'chocolatoso',
            'Gelatina nociva': 'ácido',
            'Gelatina obscura': 'maléfico',
            'Gelatina de uva': 'uva',
        }

        for name, color in expected_colors.items():
            with self.subTest(card=name):
                spells = cards[name]['spells']
                self.assertEqual(len(spells), 2)
                self.assertEqual([spell['name'] for spell in spells], ['Gelpikes', f'Hueso {color}' if color in {'descalcificado', 'chocolatoso', 'ácido', 'maléfico'} else f'Hueso de {color}'])

    def test_royal_gelatinas_use_protection_summon_and_color_spells(self):
        cards = {card['name']: card for card in serialized_cards_seed_data()}

        expected_spells = {
            'Gelatina de durazno Real': [
                'Helada Protectora',
                'Invocación de Gelatina de Durazno',
                'Hueso de durazno',
            ],
            'Gelatina de frambuesa Real': [
                'Helada Protectora',
                'Invocación de Gelatina de Frambuesa',
                'Hueso de frambuesa',
            ],
            'Gelatina lactosada Real': [
                'Helada Protectora',
                'Invocación de Gelatina lactosada',
                'Hueso descalcificado',
            ],
            'Gelatina moka Real': [
                'Helada Protectora',
                'Invocación de Gelatina moka',
                'Hueso chocolatoso',
            ],
            'Gelatina nociva Real': [
                'Helada Protectora',
                'Invocación de Gelatina nociva',
                'Hueso ácido',
            ],
            'Gelatina obscura Real': [
                'Helada Protectora',
                'Invocación de Gelatina obscura',
                'Hueso maléfico',
            ],
            'Gelatina de uva Real': [
                'Helada Protectora',
                'Invocación de Gelatina de Uva',
                'Hueso de uva',
            ],
        }

        for name, spell_names in expected_spells.items():
            with self.subTest(card=name):
                spells = cards[name]['spells']
                self.assertEqual(len(spells), 3)
                self.assertEqual([spell['name'] for spell in spells], spell_names)


class SpellBalanceTests(SimpleTestCase):
    def test_every_catalog_spell_has_positive_damage(self):
        for card in load_cards_seed_data():
            with self.subTest(card=card['name']):
                self.assertGreater(len(card['spells']), 0)
                for spell in card['spells']:
                    if 'Fusión' in spell['name']:
                        self.assertEqual(spell['damage_min'], 0, spell['name'])
                        self.assertEqual(spell['damage_max'], 0, spell['name'])
                    else:
                        self.assertGreater(spell['damage_min'], 0, spell['name'])
                        self.assertGreaterEqual(spell['damage_max'], spell['damage_min'], spell['name'])

    def test_damage_scales_with_monster_tier(self):
        cards = {card['name']: card for card in load_cards_seed_data()}

        self.assertGreaterEqual(cards['Kitsu amatista']['spells'][0]['damage_min'], 100)
        self.assertGreater(
            cards['Kitsu nishiki evolucionado']['spells'][0]['damage_min'],
            cards['Kitsu nishiki']['spells'][0]['damage_min'],
        )
        self.assertGreater(
            cards['Gelatina de durazno Real']['spells'][-1]['damage_min'],
            cards['Gelatina de durazno']['spells'][-1]['damage_min'],
        )


class BackendlessModeTests(TestCase):
    def test_index_bootstraps_seed_cards_for_local_gameplay(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cards-seed')
        self.assertContains(response, 'Modo sin Backend activo')
        self.assertContains(response, 'Nueva Partida')

    def test_frontend_keeps_catalog_and_combat_renderers(self):
        script = Path(__file__).resolve().parent / 'static' / 'core' / 'js' / 'game.js'
        source = script.read_text(encoding='utf-8')

        self.assertIn('function renderCatalog()', source)
        self.assertIn('function renderBoard(', source)
        self.assertIn('function chooseSpellForAttack(', source)

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
