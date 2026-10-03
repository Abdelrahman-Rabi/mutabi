import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from mutabi.chatgpt_auth import ChatGPTAuth, CredentialStore, ISSUER, PLAN_SCOPE
from mutabi.chatgpt_plan import ChatGPTPlanInterpreter, read_sse
from mutabi.gemini import ModelError


class Response(io.BytesIO):
    def __init__(self, body, mime='application/json'):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.headers = {'Content-Type': mime}


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.requests = []; self.responses = []; self.now = 1000
        self.auth = ChatGPTAuth(self.temp.name, transport=self.transport, clock=lambda:self.now,
            verifier=lambda token, client, nonce: {'sub':'subject', 'email':'demo@example.test'})

    def transport(self, request, timeout=30):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception): raise response
        return Response(response)

    def start(self):
        self.responses.append({'issuer':ISSUER, 'authorization_endpoint':ISSUER+'/api/accounts/authorize',
            'token_endpoint':ISSUER+'/api/accounts/oauth/token', 'jwks_uri':ISSUER+'/.well-known/jwks.json',
            'revocation_endpoint':ISSUER+'/api/accounts/oauth/revoke'})
        result = self.auth.start('http://127.0.0.1:8765/auth/callback')
        return {k:v[0] for k,v in parse_qs(urlsplit(result['authorization_url']).query).items()}

    def connect(self, scope=PLAN_SCOPE):
        params = self.start()
        self.responses.append({'access_token':'ACCESS_SECRET', 'refresh_token':'REFRESH_SECRET',
            'id_token':'ID_SECRET', 'token_type':'Bearer', 'expires_in':3600, 'scope':scope})
        if PLAN_SCOPE in scope:
            self.responses.append({'models':[{'slug':'available-model','display_name':'Available model','visibility':'list'}]})
        self.auth.callback({'state':params['state'],'code':'CODE','client_id':'oaiapp_test'})
        return params

    def test_dynamic_registration_pkce_and_stable_host(self):
        p = self.start()
        self.assertEqual(p['client_id'],'dynamic_agent_client')
        self.assertEqual(p['resource'],'https://api.openai.com/v1')
        self.assertEqual(p['code_challenge_method'],'S256')
        self.assertNotEqual(p['code_challenge'],self.auth.pending['verifier'])
        host = p['ext_agent_host_id']
        second = self.auth.start('http://127.0.0.1:8765/auth/callback')
        self.assertEqual(parse_qs(urlsplit(second['authorization_url']).query)['ext_agent_host_id'],[host])

    def test_wrong_state_cannot_exchange_or_destroy_legitimate_attempt(self):
        self.start(); count = len(self.requests)
        with self.assertRaises(ModelError):self.auth.callback({'state':'wrong','code':'CODE'})
        self.assertEqual(len(self.requests),count)
        self.assertIsNotNone(self.auth.pending)

    def test_expired_attempt_and_denial_do_not_exchange(self):
        p = self.start(); self.now += 601
        with self.assertRaises(ModelError):self.auth.callback({'state':p['state'],'code':'CODE'})
        self.assertFalse(self.auth.status()['pending'])
        p = self.auth.start('http://127.0.0.1:8765/auth/callback')
        state = parse_qs(urlsplit(p['authorization_url']).query)['state'][0]
        with self.assertRaises(ModelError):self.auth.callback({'state':state,'error':'access_denied'})
        self.assertEqual(len(self.requests),1)

    def test_success_is_one_use_and_snapshot_has_no_tokens(self):
        p = self.connect()
        self.assertTrue(self.auth.status()['ready'])
        snapshot = json.dumps(self.auth.status())
        for secret in ('ACCESS_SECRET','REFRESH_SECRET','ID_SECRET','subject'):
            self.assertNotIn(secret,snapshot)
        with self.assertRaises(ModelError):self.auth.callback({'state':p['state'],'code':'CODE','client_id':'oaiapp_test'})
        form = parse_qs(self.requests[1].data.decode())
        self.assertEqual(form['client_id'],['oaiapp_test'])
        self.assertEqual(form['redirect_uri'],['http://127.0.0.1:8765/auth/callback'])
        self.assertNotIn('client_secret',form)

    def test_identity_without_plan_permission_cannot_infer(self):
        self.connect('openid profile email')
        self.assertTrue(self.auth.status()['connected'])
        self.assertFalse(self.auth.status()['ready'])
        with self.assertRaises(ModelError):self.auth.access_token()

    def test_mismatched_returning_registration_rejected(self):
        self.connect()
        url = self.auth.start('http://127.0.0.1:8765/auth/callback')['authorization_url']
        p = parse_qs(urlsplit(url).query)
        self.assertEqual(p['client_id'],['oaiapp_test'])
        self.assertNotIn('agent_name_hint',p)
        count = len(self.requests)
        with self.assertRaises(ModelError):self.auth.callback({'state':p['state'][0],'code':'CODE','client_id':'oaiapp_other'})
        self.assertEqual(len(self.requests),count)
        self.assertTrue(self.auth.status()['connected'])

    def test_rotating_refresh_serialized_and_persisted(self):
        self.connect(); self.now += 3601
        self.responses.append({'access_token':'NEW_ACCESS','refresh_token':'NEW_REFRESH',
            'token_type':'Bearer','expires_in':3600})
        result = []
        threads = [threading.Thread(target=lambda:result.append(self.auth.access_token())) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(result,['NEW_ACCESS']*4)
        self.assertEqual(len(self.requests),4)
        self.assertEqual(self.auth.store.load()['accounts'][self.auth.data['active']]['refresh_token'],'NEW_REFRESH')

    def test_transient_refresh_failure_keeps_credentials(self):
        self.connect(); self.now += 3601
        self.responses.append(URLError('network'))
        with self.assertRaises(ModelError):self.auth.access_token()
        self.assertEqual(self.auth.active()['refresh_token'],'REFRESH_SECRET')

    def test_revoked_refresh_clears_unusable_tokens(self):
        self.connect(); self.now += 3601
        self.responses.append(HTTPError('https://auth.openai.com',400,'bad',{},io.BytesIO(b'{"error":"invalid_grant"}')))
        with self.assertRaises(ModelError):self.auth.access_token()
        self.assertFalse(self.auth.status()['connected'])
        self.assertEqual(self.auth.active()['client_id'],'oaiapp_test')

    def test_disconnect_local_clear_even_if_revocation_unavailable(self):
        self.connect(); self.responses.append(URLError('offline'))
        self.auth.disconnect()
        self.assertFalse(self.auth.status()['connected'])
        self.assertIn('not confirmed',self.auth.status()['error'])
        self.assertNotIn('refresh_token',self.auth.active())

    def test_windows_store_encrypted_and_roundtrips(self):
        import os
        if os.name != 'nt':self.skipTest('Windows DPAPI test')
        store = CredentialStore(self.temp.name)
        store.save({'secret':'NEVER_PLAINTEXT'})
        self.assertNotIn(b'NEVER_PLAINTEXT',store.path.read_bytes())
        self.assertEqual(store.load(),{'secret':'NEVER_PLAINTEXT'})

    def test_real_jwt_verification_rejects_claim_and_signature_failures(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.auth.verifier = None
        self.auth.discovery = {'jwks_uri':ISSUER+'/.well-known/jwks.json'}
        claims = {'sub':'subject','iss':ISSUER,'aud':'oaiapp_test','nonce':'expected',
                  'iat':int(time.time()),'exp':int(time.time())+300}
        with patch('jwt.PyJWKClient') as client:
            client.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key=key.public_key())
            valid = jwt.encode(claims,key,algorithm='RS256')
            self.assertEqual(self.auth.validate_identity(valid,'oaiapp_test','expected')['sub'],'subject')
            for changed in ({'nonce':'wrong'},{'aud':'other'},{'iss':'https://attacker.test'},{'exp':1}):
                with self.subTest(changed=changed), self.assertRaises(ModelError):
                    self.auth.validate_identity(jwt.encode({**claims,**changed},key,algorithm='RS256'),'oaiapp_test','expected')
            other = rsa.generate_private_key(public_exponent=65537,key_size=2048)
            with self.assertRaises(ModelError):self.auth.validate_identity(jwt.encode(claims,other,algorithm='RS256'),'oaiapp_test','expected')


class StreamTests(unittest.TestCase):
    def response(self, events):
        return Response(b''.join(('data: '+json.dumps(event,ensure_ascii=False)+'\r\n\r\n').encode() for event in events),'text/event-stream')

    def completion(self, decision):
        return {'type':'response.completed','response':{'status':'completed','usage':{'input_tokens':12},
            'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(decision,ensure_ascii=False)}]}]}}

    def test_complete_response_validates_evidence_and_exact_request_contract(self):
        text = 'I will pay SAR 3,000 on October 5, 2026.'
        decision = {'intent':'payment_promise','amount':'3000','payment_date':'2026-10-05',
            'date_requires_confirmation':False,'reason':'Explicit','amount_evidence':'SAR 3,000','date_evidence':'October 5, 2026'}
        requests = []
        def transport(request,timeout):
            requests.append(request)
            return self.response([{'type':'response.output_text.delta','delta':'partial'},self.completion(decision)])
        auth = SimpleNamespace(access_token=lambda:'PRIVATE_TOKEN',status=lambda:{'model':'account-model'})
        adapter = ChatGPTPlanInterpreter(auth,transport)
        self.assertEqual(adapter.interpret(text,'2026-10-03')['amount'],'3000')
        payload = json.loads(requests[0].data)
        self.assertFalse(payload['store']);self.assertTrue(payload['stream'])
        self.assertEqual(payload['text']['format']['type'],'json_schema')
        self.assertNotIn('temperature',payload);self.assertNotIn('max_output_tokens',payload)
        self.assertEqual(adapter.last_metadata['provider'],'chatgpt_plan')

    def test_partial_and_incomplete_output_never_accepted(self):
        for events in ([{'type':'response.output_text.delta','delta':'{}'}],
                       [{'type':'response.incomplete','response':{}}]):
            with self.subTest(events=events),self.assertRaises(ModelError):read_sse(self.response(events))

    def test_gateway_missing_content_type_still_requires_complete_sse(self):
        decision = {'intent':'unknown','amount':None,'payment_date':None,
            'date_requires_confirmation':False,'reason':'No commitment','amount_evidence':None,'date_evidence':None}
        response = self.response([self.completion(decision)])
        response.headers = {}
        auth = SimpleNamespace(access_token=lambda:'PRIVATE',status=lambda:{'model':'model'})
        adapter = ChatGPTPlanInterpreter(auth,lambda request,timeout:response)
        self.assertEqual(adapter.interpret('Hello','2026-10-03')['intent'],'unknown')
        for body in (b'{}',b'event: response.output_text.delta\ndata: {}\n\n'):
            response = Response(body,'text/event-stream');response.headers={}
            adapter = ChatGPTPlanInterpreter(auth,lambda request,timeout:response)
            with self.assertRaises(ModelError):adapter.interpret('Hello','2026-10-03')

    def test_usage_error_after_stream_started_safe(self):
        events = [{'type':'response.output_text.delta','delta':'partial'},
            {'type':'response.failed','response':{'error':{'code':'subscription_sharing_usage_limit_exceeded','message':'SECRET'}}}]
        with self.assertRaises(ModelError) as error:read_sse(self.response(events))
        self.assertIn('usage limit',str(error.exception));self.assertNotIn('SECRET',str(error.exception))

    def test_finalized_item_without_completion_output_requires_terminal_success(self):
        event = {'type':'response.output_item.done','output_index':0,'item':{
            'type':'message','status':'completed','content':[{'type':'output_text','text':'{"intent":"unknown"}'}]}}
        completion = {'type':'response.completed','response':{'status':'completed','output':[]}}
        self.assertEqual(read_sse(self.response([event,completion]))[0],'{"intent":"unknown"}')
        for ending in ([],[{'type':'response.incomplete','response':{}}]):
            with self.assertRaises(ModelError):read_sse(self.response([event]+ending))

    def test_arabic_utf8_and_multiline_sse(self):
        event = self.completion({'reason':'وعد سداد'})
        body = json.dumps(event,ensure_ascii=False,indent=2)
        response = Response(('\n'.join('data: '+line for line in body.splitlines())+'\n\n').encode(),'text/event-stream')
        self.assertIn('وعد سداد',read_sse(response)[0])

    def test_refusal_rejected(self):
        event = self.completion({})
        event['response']['output'][0]['content']=[{'type':'refusal','refusal':'No'}]
        with self.assertRaises(ModelError):read_sse(self.response([event]))

    def test_fabricated_evidence_rejected(self):
        decision = {'intent':'payment_promise','amount':'999','payment_date':None,
            'date_requires_confirmation':False,'reason':'Bad','amount_evidence':'999','date_evidence':None}
        auth = SimpleNamespace(access_token=lambda:'PRIVATE',status=lambda:{'model':'model'})
        adapter = ChatGPTPlanInterpreter(auth,lambda request,timeout:self.response([self.completion(decision)]))
        with self.assertRaises(ModelError):adapter.interpret('I will pay 3000.','2026-10-03')


if __name__ == '__main__':unittest.main()
