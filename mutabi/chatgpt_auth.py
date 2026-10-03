"""Local public-client OAuth for Mutabi; never reads Codex credentials."""
import base64
import ctypes
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from .gemini import ModelError

ISSUER = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
PLAN_SCOPE = 'chatgpt.tokens.use.direct'
SCOPES = 'openid profile email offline_access resource.invoke ' + PLAN_SCOPE


def dpapi(data, decrypt=False):
    """Windows user-bound protection, with interactive prompts forbidden."""
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    name = 'CryptUnprotectData' if decrypt else 'CryptProtectData'
    method = getattr(crypt, name)
    method.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    method.restype = wintypes.BOOL
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ModelError('Could not protect or open the local ChatGPT credentials.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(output.data)


class CredentialStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'credentials.bin'

    def write_bytes(self, path, data):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != 'nt':
            os.chmod(self.directory, 0o700)
        temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def load(self):
        if not self.path.exists():
            return {'accounts': {}, 'active': None}
        try:
            data = self.path.read_bytes()
            if os.name == 'nt':
                data = dpapi(data, decrypt=True)
            return json.loads(data)
        except (ValueError, OSError):
            raise ModelError('Could not open local ChatGPT credentials. Reconnect from settings.') from None

    def save(self, value):
        data = json.dumps(value).encode()
        if os.name == 'nt':
            data = dpapi(data)
        self.write_bytes(self.path, data)

    def host_id(self):
        path = self.directory / 'host-id.txt'
        if path.exists():
            return path.read_text().strip()
        value = 'urn:uuid:' + str(uuid4())
        self.write_bytes(path, value.encode())
        return value


class ChatGPTAuth:
    def __init__(self, directory, transport=urlopen, verifier=None, clock=time.time, store=None):
        self.store = store or CredentialStore(directory)
        self.data = self.store.load()
        self.transport, self.verifier, self.clock = transport, verifier, clock
        self.lock = threading.RLock()
        self.pending = None
        self.discovery = None
        self.models = []
        self.connection_error = None
        self.welcome = False

    def request_json(self, request):
        try:
            with self.transport(request, timeout=30) as response:
                return json.loads(response.read(1024 * 1024))
        except HTTPError as error:
            code = None
            try:
                body = json.loads(error.read(8192))
                code = body.get('error', {}).get('code') if isinstance(body.get('error'), dict) else body.get('error')
            except (ValueError, AttributeError):
                pass
            message = 'ChatGPT connection request failed. Try again later.'
            if code in ('invalid_grant', 'invalid_refresh_token', 'token_expired',
                        'refresh_token_expired', 'refresh_token_invalidated', 'refresh_token_reused'):
                message = 'ChatGPT authorization expired or was revoked. Reconnect your account.'
            error_safe = ModelError(message, error.code)
            error_safe.oauth_code = code
            raise error_safe from None
        except (URLError, TimeoutError, ValueError):
            raise ModelError('Could not contact ChatGPT authorization. Try again later.') from None

    def endpoints(self):
        if self.discovery is None:
            value = self.request_json(Request(ISSUER + '/.well-known/openid-configuration'))
            if value.get('issuer') != ISSUER:
                raise ModelError('ChatGPT identity configuration was not valid.')
            # Do not let discovery redirect credentials to an arbitrary origin.
            for key in ('authorization_endpoint', 'token_endpoint', 'jwks_uri', 'revocation_endpoint'):
                if not value.get(key, '').startswith(ISSUER + '/'):
                    raise ModelError('ChatGPT identity configuration was not valid.')
            self.discovery = value
        return self.discovery

    def active(self):
        return self.data['accounts'].get(self.data.get('active'))

    def status(self):
        with self.lock:
            if self.pending and self.pending['expires'] <= self.clock():
                self.pending = None
                self.connection_error = 'ChatGPT sign-in timed out. Try connecting again.'
            account = self.active()
            permission = bool(account and PLAN_SCOPE in account.get('scopes', []))
            return {'connected': bool(account and account.get('access_token')),
                    'plan_enabled': permission,
                    'ready': bool(permission and account.get('access_token') and account.get('model')),
                    'account': account.get('email') if account else None,
                    'model': account.get('model') if account else None,
                    'models': self.models,
                    'accounts': [{'id': key, 'label': r.get('email', 'ChatGPT account') + ' · ' + str(i + 1)}
                                 for i, (key, r) in enumerate(self.data['accounts'].items())],
                    'active_account': self.data.get('active'), 'pending': bool(self.pending),
                    'error': self.connection_error, 'show_welcome': self.welcome}

    def start(self, callback_uri, new_account=False):
        with self.lock:
            # Dependency check happens before the browser is sent through OAuth.
            if self.verifier is None:
                try:
                    import jwt  # noqa: F401
                except ImportError:
                    raise ModelError('Install requirements.txt to enable ChatGPT sign-in.') from None
            endpoints = self.endpoints()
            account = None if new_account else self.active()
            verifier = secrets.token_urlsafe(64)
            pending = {'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32),
                       'verifier': verifier, 'redirect_uri': callback_uri, 'expires': self.clock() + 600,
                       'client_id': account['client_id'] if account else 'dynamic_agent_client',
                       'subject': account['subject'] if account else None}
            parameters = {'client_id': pending['client_id'], 'ext_agent_host_id': self.store.host_id(),
                          'response_type': 'code', 'redirect_uri': callback_uri, 'scope': SCOPES,
                          'resource': RESOURCE, 'state': pending['state'], 'nonce': pending['nonce'],
                          'code_challenge_method': 'S256',
                          'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
            if account:
                # No id_token_hint in URLs; keep tokens out of browser-visible URLs.
                if account.get('email'):
                    parameters['login_hint'] = account['email']
                if PLAN_SCOPE not in account.get('scopes', []):
                    parameters['prompt'] = 'consent'
            else:
                parameters['agent_name_hint'] = 'Mutabi'
            self.pending, self.connection_error = pending, None
            return {'authorization_url': endpoints['authorization_endpoint'] + '?' + urlencode(parameters)}

    def validate_identity(self, token, client_id, nonce):
        if self.verifier:
            return self.verifier(token, client_id, nonce)
        try:
            import jwt
            keys = jwt.PyJWKClient(self.endpoints()['jwks_uri'])
            key = keys.get_signing_key_from_jwt(token)
            value = jwt.decode(token, key.key, algorithms=['RS256'], audience=client_id,
                               issuer=ISSUER, options={'require': ['sub', 'exp', 'iat', 'nonce']}, leeway=5)
            if not secrets.compare_digest(str(value['nonce']), nonce) or not value['sub']:
                raise ValueError('Invalid nonce')
            return value
        except Exception:
            raise ModelError('ChatGPT identity validation failed. Start sign-in again.') from None

    def _tokens(self, body, previous=None):
        if not isinstance(body.get('access_token'), str) or body.get('token_type', '').lower() != 'bearer':
            raise ModelError('ChatGPT returned incomplete authorization credentials.')
        expiry = body.get('expires_in')
        if not isinstance(expiry, (int, float)) or not 0 < expiry < 86400:
            raise ModelError('ChatGPT returned invalid authorization expiry.')
        result = dict(previous or {})
        for name in ('access_token', 'refresh_token', 'id_token'):
            if body.get(name):
                result[name] = body[name]
        result['expires_at'] = self.clock() + expiry
        result['scopes'] = body.get('scope', ' '.join(result.get('scopes', []))).split()
        return result

    def callback(self, parameters):
        with self.lock:
            pending = self.pending
            if not pending or pending['expires'] <= self.clock() or not secrets.compare_digest(
                    parameters.get('state', ''), pending['state']):
                raise ModelError('Invalid or expired ChatGPT sign-in attempt.')
            self.pending = None  # One use even if the exchange/validation fails.
            try:
                if parameters.get('error'):
                    raise ModelError('ChatGPT connection was cancelled or permission was declined.')
                client_id = parameters.get('client_id', pending['client_id'])
                if pending['client_id'] == 'dynamic_agent_client':
                    if not client_id.startswith('oaiapp_'):
                        raise ModelError('ChatGPT registration did not return an issued client ID.')
                elif client_id != pending['client_id']:
                    raise ModelError('ChatGPT returned a different account registration.')
                if not parameters.get('code'):
                    raise ModelError('ChatGPT sign-in did not return an authorization code.')
                form = {'grant_type': 'authorization_code', 'client_id': client_id,
                        'code': parameters['code'], 'code_verifier': pending['verifier'],
                        'redirect_uri': pending['redirect_uri'], 'resource': RESOURCE}
                body = self.request_json(Request(self.endpoints()['token_endpoint'], data=urlencode(form).encode()))
                identity = self.validate_identity(body.get('id_token', ''), client_id, pending['nonce'])
                if pending['subject'] and identity['sub'] != pending['subject']:
                    raise ModelError('ChatGPT sign-in returned a different account. Add it separately.')
                key = hashlib.sha256((client_id + ':' + identity['sub']).encode()).hexdigest()
                previous = self.data['accounts'].get(key, {})
                record = self._tokens(body)
                record.update(client_id=client_id, subject=identity['sub'],
                              email=identity.get('email', 'ChatGPT account'), model=previous.get('model'))
                self.data['accounts'][key] = record; self.data['active'] = key
                self.store.save(self.data)
                self.welcome = PLAN_SCOPE in record['scopes']
                if self.welcome:
                    try:
                        self.load_models()
                    except ModelError as error:
                        self.connection_error = str(error)
                return self.status()
            except ModelError as error:
                self.connection_error = str(error)
                raise

    def access_token(self):
        with self.lock:
            account = self.active()
            if not account or not account.get('access_token'):
                raise ModelError('Connect ChatGPT before analyzing a reply.')
            if PLAN_SCOPE not in account.get('scopes', []):
                raise ModelError('ChatGPT plan permission is disabled. Reconnect to enable it.')
            if account['expires_at'] - self.clock() < 30:
                if not account.get('refresh_token'):
                    raise ModelError('ChatGPT authorization expired. Reconnect your account.')
                form = {'grant_type': 'refresh_token', 'client_id': account['client_id'],
                        'refresh_token': account['refresh_token'], 'resource': RESOURCE}
                try:
                    body = self.request_json(Request(self.endpoints()['token_endpoint'], data=urlencode(form).encode()))
                except ModelError as error:
                    if getattr(error, 'oauth_code', None) in ('invalid_grant', 'invalid_refresh_token',
                            'token_expired', 'refresh_token_expired', 'refresh_token_invalidated', 'refresh_token_reused'):
                        for name in ('access_token', 'refresh_token', 'id_token'):
                            account.pop(name, None)
                        self.store.save(self.data)
                    raise
                updated = self._tokens(body, account)
                self.data['accounts'][self.data['active']] = updated
                self.store.save(self.data)
                account = updated
                if PLAN_SCOPE not in account['scopes']:
                    raise ModelError('ChatGPT plan permission is disabled. Reconnect to enable it.')
            return account['access_token']

    def load_models(self):
        with self.lock:
            body = self.request_json(Request(RESOURCE + '/models', headers={'Authorization': 'Bearer ' + self.access_token()}))
            catalog = body.get('models', [])
            self.models = [{'slug': r['slug'], 'display_name': r.get('display_name', r['slug'])}
                           for r in catalog if r.get('visibility') == 'list' and isinstance(r.get('slug'), str)]
            if not self.models:
                raise ModelError('No ChatGPT plan models are available for this account.')
            account = self.active()
            if account.get('model') not in [r['slug'] for r in self.models]:
                account['model'] = self.models[0]['slug']
            self.store.save(self.data)
            self.connection_error = None
            return self.status()

    def select_model(self, model):
        with self.lock:
            if model not in [r['slug'] for r in self.models]:
                raise ValueError('Select a model from the current ChatGPT account catalog')
            self.active()['model'] = model; self.store.save(self.data)
            return self.status()

    def select_account(self, key):
        with self.lock:
            if key not in self.data['accounts']:
                raise ValueError('Unknown ChatGPT account')
            self.pending = None; self.data['active'] = key; self.models = []
            self.store.save(self.data)
            return self.load_models()

    def disconnect(self):
        with self.lock:
            account = self.active(); confirmed = True; self.pending = None
            if account and account.get('refresh_token'):
                try:
                    request = Request(self.endpoints()['revocation_endpoint'], data=urlencode({
                        'token': account['refresh_token'], 'token_type_hint': 'refresh_token',
                        'client_id': account['client_id']}).encode())
                    with self.transport(request, timeout=30):
                        pass
                except (HTTPError, URLError, TimeoutError, ModelError):
                    confirmed = False
            if account:
                for name in ('access_token', 'refresh_token', 'id_token'):
                    account.pop(name, None)
                self.store.save(self.data)
            self.models = []; self.welcome = False
            self.connection_error = None if confirmed else 'Disconnected locally. Remote revocation was not confirmed; disconnect Mutabi in ChatGPT settings.'
            return self.status()
