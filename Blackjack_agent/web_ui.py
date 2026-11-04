"""표준 라이브러리만 사용하는 루프백 HTTP 서버. 엔진은 Python에서 실행."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
import json
import secrets
import webbrowser

from agents import make_agents
from game import Game, Settings

WEB_ROOT = Path(__file__).with_name('web')


class SimulatorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=0):
        super().__init__(('127.0.0.1', port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.game = None
        self.lock = Lock()
        self.sequence = 0
        self.game_id = 0

    def advance(self):
        if not self.game:
            raise ValueError('먼저 시뮬레이션을 시작하세요.')
        event = next(self.game.events, None)
        if event:
            self.sequence += 1
            event['sequence'] = self.sequence
        return event


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, payload, content_type='application/json; charset=utf-8'):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if isinstance(payload, dict) else payload
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8')}
        entry = files.get(self.path)
        if not entry:
            self.respond(404, {'error': 'Not found'})
            return
        name, mime = entry
        self.respond(200, (WEB_ROOT / name).read_bytes(), mime)

    def do_POST(self):
        if not secrets.compare_digest(self.headers.get('X-Session-Token', ''), self.server.token):
            self.respond(403, {'error': '실행 시 표시된 브라우저 주소로 접속하세요.'})
            return
        if self.path not in ('/api/start', '/api/step', '/api/reset'):
            self.respond(404, {'error': 'Not found'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192:
                raise ValueError('요청 크기가 올바르지 않습니다.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('설정 형식이 올바르지 않습니다.')
            cfg = None
            if self.path == '/api/start':
                values = data.get('settings', {})
                if not isinstance(values, dict) or any(type(v) is not int for v in values.values()):
                    raise ValueError('설정값은 정수여야 합니다.')
                cfg = Settings(**values)
                cfg.validate()
            if self.path in ('/api/start', '/api/reset') and self.server.game:
                self.server.game.cancel()
            with self.server.lock:
                if self.path == '/api/start':
                    self.server.game = Game(cfg, make_agents(cfg))
                    self.server.game_id += 1
                    self.server.sequence = 0
                    payload = {'event': self.server.advance(), 'settings': vars(cfg), 'game_id': self.server.game_id}
                elif self.path == '/api/reset':
                    self.server.game = None
                    self.server.game_id += 1
                    self.server.sequence = 0
                    payload = {'reset': True}
                else:
                    if data.get('game_id') != self.server.game_id:
                        raise ValueError('이전 게임의 요청입니다. 새 게임에서 다시 진행하세요.')
                    payload = {'event': self.server.advance()}
            self.respond(200, payload)
        except (ValueError, TypeError, OverflowError) as error:
            self.respond(400, {'error': str(error)})
        except Exception as error:
            self.respond(500, {'error': f'계산이 중단되었습니다: {type(error).__name__}'})


def launch(port=0, open_browser=True):
    server = SimulatorServer(port)
    url = f'http://127.0.0.1:{server.server_port}/#{server.token}'
    print(f'Blackjack HTML UI: {url}', flush=True)
    print('Stop server: Ctrl+C', flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server.game:
            server.game.cancel()
        server.server_close()
