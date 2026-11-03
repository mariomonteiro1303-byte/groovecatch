"""Testes offline: a pesquisa geográfica não pode retornar rádios irrelevantes."""
import unittest
from unittest.mock import patch
# Carrega o serviço isoladamente, sem exigir Flask no ambiente de testes.
import importlib.util
import sys
from pathlib import Path
module_path = Path(__file__).resolve().parents[1] / 'app/services/radio_service.py'
spec = importlib.util.spec_from_file_location('radio_service_under_test', module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
RadioBrowserProvider = module.RadioBrowserProvider

class RadioSearchTests(unittest.TestCase):
    def setUp(self):
        self.provider = RadioBrowserProvider()
        self.rows = [
            {"stationuuid":"1", "name":"Rádio Teresina", "city":"Teresina", "state":"Piauí", "country":"Brazil", "url":"https://example.com/1", "votes":2},
            {"stationuuid":"2", "name":"Jazz FM", "city":"New York", "state":"New York", "country":"United States", "url":"https://example.com/2", "votes":900},
            {"stationuuid":"3", "name":"Grande FM", "city":"Picos", "state":"Piauí", "country":"Brazil", "url":"https://example.com/3", "votes":1},
        ]
    def test_city_does_not_include_other_countries(self):
        with patch.object(self.provider, '_field_search', return_value=self.rows):
            found = self.provider.search('Teresina', field='city')
        self.assertEqual([x['id'] for x in found], ['1'])
    def test_state_accepts_accent_insensitive(self):
        with patch.object(self.provider, '_field_search', return_value=self.rows):
            found = self.provider.search('Piaui', field='state')
        self.assertEqual({x['id'] for x in found}, {'1','3'})
    def test_unknown_city_empty_not_global_fallback(self):
        with patch.object(self.provider, '_field_search', return_value=self.rows):
            found = self.provider.search('Cidade Inexistente', field='city')
        self.assertEqual(found, [])
    def test_auto_only_relevant_results(self):
        with patch.object(self.provider, '_field_search', return_value=self.rows):
            found = self.provider.search('Teresina')
        self.assertEqual([x['id'] for x in found], ['1'])

if __name__ == '__main__': unittest.main()
