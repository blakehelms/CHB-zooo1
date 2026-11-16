"""Local browser application. Standard library only; optional OpenMuse hardware stack."""
from collections import deque
import fcntl
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import secrets
import signal
import ssl
import sys
import threading
import time
from urllib.parse import urlsplit
import webbrowser
from .controller import Controller, BenchWriter

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).parent / 'static'


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


class Access:
    def __init__(self, root, password=None):
        self.file = Path(root) / '.local' / 'auth.json'
        self.lock = threading.RLock()
        self.sessions = {}
        self.attempts = deque(maxlen=20)
        self.secret = json.loads(self.file.read_text()) if self.file.exists() else None
        if password:
            self.configure(password, persist=False)

    def configure(self, password, persist=True):
        if not isinstance(password, str) or len(password) < 8 or len(password) > 256:
            raise ValueError('Use a researcher password of 8–256 characters.')
        salt = secrets.token_hex(16)
        self.secret = {'salt': salt, 'hash': password_hash(password, salt)}
        if persist:
            self.file.parent.mkdir(mode=0o700, exist_ok=True)
            with self.file.open('w') as f:
                os.chmod(self.file, 0o600)
                json.dump(self.secret, f)
        self.sessions.clear()

    def login(self, password):
        with self.lock:
            now = time.monotonic()
            while self.attempts and self.attempts[0] < now - 60:
                self.attempts.popleft()
            if len(self.attempts) >= 6:
                raise ValueError('Too many attempts. Wait a minute and try again.')
            self.attempts.append(now)
            if not self.secret or not hmac.compare_digest(password_hash(password, self.secret['salt']), self.secret['hash']):
                raise ValueError('Password not recognized.')
            self.sessions = {k: v for k, v in self.sessions.items() if v[0] > now}
            if len(self.sessions) >= 32:
                self.sessions.pop(next(iter(self.sessions)))
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.sessions[token] = (now + 12*3600, csrf)
            return token

    def session(self, cookie):
        try:
            parsed = SimpleCookie(cookie or '')
            token = parsed['zooo1'].value
        except (KeyError, ValueError):
            return None
        with self.lock:
            value = self.sessions.get(token)
            return value if value and value[0] > time.monotonic() else None


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = 'zooo1'
    sys_version = ''
    def log_message(self, *args):
        pass  # Never log request data, paths, cookies, or participant fields.

    def reply(self, status, data, kind='application/json', cookie=None):
        if kind == 'application/json':
            data = json.dumps(data, allow_nan=False).encode()
        elif isinstance(data, str):
            data = data.encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def guard(self):
        # Exact Host/Origin validation also blocks DNS rebinding and cross-site requests.
        return self.headers.get('Host') in self.server.allowed_hosts

    def do_GET(self):
        if not self.guard():
            return self.reply(403, {'error': 'Address not authorized.'})
        path = urlsplit(self.path).path
        session = self.server.access.session(self.headers.get('Cookie'))
        if path == '/api/access':
            return self.reply(200, {'authenticated': bool(session), 'csrf': session[1] if session else None,
                                    'setup': self.server.access.secret is None and self.server.local,
                                    'setup_token': self.server.setup_token if self.server.access.secret is None and self.server.local else None})
        if path == '/api/state':
            return self.reply(200, self.server.controller.snapshot()) if session else self.reply(401, {'error': 'Researcher login required.'})
        assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/monitor': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path not in assets:
            return self.reply(404, {'error': 'Page not found.'})
        name, kind = assets[path]
        self.reply(200, (STATIC / name).read_bytes(), kind)

    def do_POST(self):
        expected_origin = ('https://' if self.server.encrypted else 'http://') + self.headers.get('Host', '')
        if not self.guard() or self.headers.get('Origin') != expected_origin:
            return self.reply(403, {'error': 'Request not authorized.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096 or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Invalid request.')
            self.connection.settimeout(5)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Invalid request.')
        except (ValueError, OSError):
            return self.reply(400, {'error': 'Invalid request.'})
        path = urlsplit(self.path).path
        access = self.server.access
        try:
            if path in ('/api/login', '/api/setup'):
                password = data.get('password')
                if not isinstance(password, str) or not 1 <= len(password) <= 256:
                    raise ValueError('Enter a valid password.')
                with access.lock:
                    if path == '/api/setup':
                        if access.secret or not self.server.local or not hmac.compare_digest(self.headers.get('X-Setup', ''), self.server.setup_token):
                            return self.reply(403, {'error': 'Local setup is unavailable.'})
                        access.configure(password)
                    token = access.login(password)
                cookie = 'zooo1=' + token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200' + ('; Secure' if self.server.encrypted else '')
                return self.reply(200, {'ok': True}, cookie=cookie)
            session = access.session(self.headers.get('Cookie'))
            if not session:
                return self.reply(401, {'error': 'Researcher login required.'})
            if not hmac.compare_digest(session[1], self.headers.get('X-CSRF', '')):
                return self.reply(403, {'error': 'Reload this page and try again.'})
            controller = self.server.controller
            if path == '/api/start':
                controller.begin(data)
            elif path == '/api/end':
                controller.end()
            elif path == '/api/reset':
                controller.reset()
            elif path == '/api/marker':
                controller.marker()
            elif path == '/api/logout':
                with access.lock:
                    for key, value in list(access.sessions.items()):
                        if value == session:
                            del access.sessions[key]
                return self.reply(200, {'ok': True}, cookie='zooo1=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/')
            else:
                return self.reply(404, {'error': 'Action not found.'})
            return self.reply(200, {'ok': True})
        except ValueError as exc:
            self.reply(409, {'error': str(exc)})
        except Exception:
            self.reply(503, {'error': 'Action failed. Check the researcher monitor before continuing.'})


def make_server(root=ROOT, port=8765, host='127.0.0.1', controller=None):
    local = host in ('127.0.0.1', '::1', 'localhost')
    cert, key = os.environ.get('ZOOO1_TLS_CERT'), os.environ.get('ZOOO1_TLS_KEY')
    if not local and not (cert and key and os.environ.get('ZOOO1_APPROVED_NETWORK') == 'yes' and os.environ.get('ZOOO1_HOSTS')):
        raise RuntimeError('Remote access requires TLS, an approved network, and an explicit hostname allowlist. See docs/PI-SETUP.md.')
    access = Access(root, os.environ.get('ZOOO1_PASSWORD'))
    if not local and not access.secret:
        raise RuntimeError('Configure a local secret before enabling remote access.')
    if controller is None:
        factory = (lambda: BenchWriter(Path(root) / 'bench-recordings')) if os.environ.get('ZOOO1_BENCH_RECORDING') == 'yes' else None
        controller = Controller(root, writer_factory=factory)
    server = Server((host, port), Handler)
    server.local, server.encrypted = local, bool(cert and key)
    server.controller, server.access = controller, access
    server.setup_token = secrets.token_urlsafe(32)
    actual_port = server.server_address[1]
    server.allowed_hosts = {f'127.0.0.1:{actual_port}', f'localhost:{actual_port}'} if local else set()
    server.allowed_hosts.update(x.strip() for x in os.environ.get('ZOOO1_HOSTS', '').split(',') if x.strip())
    if cert and key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    return server


def main():
    os.umask(0o077)
    ROOT.joinpath('.local').mkdir(mode=0o700, exist_ok=True)
    lock = ROOT.joinpath('.local/service.lock').open('a')
    host = os.environ.get('ZOOO1_BIND', '127.0.0.1')
    port = int(os.environ.get('ZOOO1_PORT', '8765'))
    url = ('https' if os.environ.get('ZOOO1_TLS_CERT') else 'http') + '://127.0.0.1:' + str(port)
    if '--no-browser' not in sys.argv:
        from .viewer import launch_desktop_viewer
        launch_desktop_viewer(ROOT)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if '--no-browser' not in sys.argv and host == '127.0.0.1':
            webbrowser.open(url)
        return
    server = make_server(port=port, host=host)
    worker = threading.Thread(target=server.controller.run, name='acquisition-owner', daemon=True)
    worker.start()
    def shutdown(*_):
        server.controller.stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    if '--no-browser' not in sys.argv and host == '127.0.0.1':
        threading.Timer(.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        server.controller.stop.set()
        worker.join(timeout=30)
        server.server_close()
        lock.close()


if __name__ == '__main__':
    main()
