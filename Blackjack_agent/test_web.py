"""로컬 HTML 서버 통합 검사. python -m unittest tests test_web -v"""
from http.client import HTTPConnection
import json
from threading import Thread
import unittest
from web_ui import SimulatorServer


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = SimulatorServer()
        cls.worker = Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def request(self, path, data=None, token=True):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        headers = {'X-Session-Token': self.server.token} if token else {}
        connection.request('POST' if data is not None else 'GET', path,
                           json.dumps(data) if data is not None else None, headers)
        response = connection.getresponse()
        status, payload = response.status, response.read()
        connection.close()
        return status, payload

    def test_static_files(self):
        for path, content in [('/', b'BLACKJACK'), ('/app.js', b'async function step'), ('/style.css', b'.felt')]:
            status, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn(content, body)
        self.assertEqual(self.request('/../game.py')[0], 404)

    def test_authentication_and_invalid_settings(self):
        self.assertEqual(self.request('/api/start', {}, token=False)[0], 403)
        self.assertEqual(self.request('/api/start', {'settings': {'minimum': -1}})[0], 400)
        self.assertEqual(self.request('/api/start', {'settings': {'samples_a': '20'}})[0], 400)

    def test_complete_game_and_reset(self):
        status, payload = self.request('/api/start', {'settings': {'depth_a': 1, 'depth_b': 1, 'samples_a': 1, 'samples_b': 1}})
        self.assertEqual(status, 200)
        data = json.loads(payload)
        game_id, event = data['game_id'], data['event']
        self.assertEqual(event['action'], 'ORDER')
        sequence = 1
        while not event['state']['game_over']:
            status, payload = self.request('/api/step', {'game_id': game_id})
            self.assertEqual(status, 200)
            event = json.loads(payload)['event']
            sequence += 1
            self.assertEqual(event['sequence'], sequence)
            self.assertNotIn('_deck', event['state'])
        self.assertEqual(len(event['state']['records']), 10)
        self.assertEqual(self.request('/api/reset', {})[0], 200)
        self.assertEqual(self.request('/api/step', {'game_id': game_id})[0], 400)


if __name__ == '__main__':
    unittest.main()
