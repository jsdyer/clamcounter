import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from catalogue import validate

DATA = json.loads((Path(__file__).resolve().parents[1] / 'web/data/catalogue.json').read_text())


class CatalogueTests(unittest.TestCase):
    def test_real_menu_evidence_keeps_unknowns(self):
        validate(DATA)
        market = next(x for x in DATA['items'] if x['restaurant_id'] == 'mic-mac')
        self.assertIsNone(market['cents'])
        tasty = next(x for x in DATA['items'] if x['restaurant_id'] == 'tasty-pizza')
        self.assertEqual(tasty['portion'], 'Two cups of clams')
        self.assertEqual(tasty['type'], 'unspecified')

    def test_rejects_fractional_cents_and_orphans(self):
        for key, value in [('cents', 29.95), ('cents', True), ('cents', -1), ('restaurant_id', 'missing'), ('type', 'probably-whole'), ('tax_included', True)]:
            data = copy.deepcopy(DATA); data['items'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate(data)

    def test_hours_distinguish_closed_unknown_and_overnight(self):
        data = copy.deepcopy(DATA)
        data['restaurants'][0]['week'] = [[], None, [660, 1560], [660, 1200], [], [], []]
        validate(data)
        for bad in [[660, 120], [-1, 600], [1500, 1560], [0, 1500], [660], [True, 600]]:
            data['restaurants'][0]['week'][0] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate(data)

    def test_expands_restaurants_and_dishes_without_a_fixed_count(self):
        data = copy.deepcopy(DATA)
        new = {**data['restaurants'][0], 'id': 'additional', 'source_id': 'additional'}
        data['restaurants'].append(new)
        data['items'].append({**data['items'][0], 'id': 'additional-dish', 'restaurant_id': 'additional'})
        validate(data)

    def test_rejects_duplicate_ids_and_unsafe_sources(self):
        data = copy.deepcopy(DATA); data['items'].append(data['items'][0])
        with self.assertRaises(ValueError): validate(data)
        data = copy.deepcopy(DATA); data['restaurants'][0]['menu_url'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError): validate(data)


if __name__ == '__main__': unittest.main()
