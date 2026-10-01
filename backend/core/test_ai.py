import json,uuid
from unittest.mock import patch,MagicMock
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from .models import OrgUnit,Membership,Asset,WorkOrder,AIConfiguration,AIRequest,AuditEvent
from .auth import cipher
from .ai import resolved_address,complete

@override_settings(DEBUG=True,MFA_REQUIRED=False,SECURE_SSL_REDIRECT=False,AI_PRIVATE_ORIGINS=[])
class AITests(TestCase):
    def setUp(self):
        U=get_user_model();self.user=U.objects.create_user('ai-user',password='test-password-ai');self.admin=U.objects.create_superuser('ai-admin',password='test-password-ai')
        self.org=OrgUnit.objects.create(name='A',kind='church');self.other=OrgUnit.objects.create(name='B',kind='church')
        self.grant=Membership.objects.create(user=self.user,org=self.org,role='worker')
        self.asset=Asset.objects.create(org=self.org,name='Hus',kind='property')
        self.work=WorkOrder.objects.create(org=self.org,asset=self.asset,number=1,title='Pump',description='DO NOT SEND INTERNAL',reporter_email='private@example.invalid')
        otherasset=Asset.objects.create(org=self.other,name='Other',kind='property')
        self.secret=WorkOrder.objects.create(org=self.other,asset=otherasset,number=2,title='SECRET OTHER BRANCH')
        self.cfg=AIConfiguration.objects.create(enabled=True,model='test-model',encrypted_api_key=cipher().encrypt(b'provider-secret').decode(),allow_changes=True)
        self.cfg.organizations.set([self.org,self.other]);self.client=APIClient();self.client.force_login(self.user)
        session=self.client.session;session['security_version']=1;session.save()
    def post(self,path,data,key=None):return self.client.post('/api/v1/ai/'+path,data,format='json',HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()))
    def ask(self,**extra):
        context=self.client.get('/api/v1/ai/context/',{'org':str(self.org.pk)})
        self.assertEqual(context.status_code,200,context.data)
        return self.post('chat/',{'org':str(self.org.pk),'question':'Föreslå prioritet','context_digest':context.data['digest'],**extra})
    def reply(self):return {'answer':'Se arbetsorder #1.','proposals':[{'id':str(self.work.pk),'priority':'high','reason':'Kontrollera pumpen'}]}
    @patch('core.ai.complete')
    def test_scoped_context_and_explicit_apply(self,m):
        m.return_value=self.reply();r=self.ask();self.assertEqual(r.status_code,200,r.data)
        sent=json.dumps(m.call_args.args[2]);self.assertNotIn('SECRET',sent);self.assertNotIn('DO NOT SEND',sent);self.assertNotIn('private@',sent)
        self.work.refresh_from_db();self.assertEqual(self.work.priority,'normal')
        token=r.data['proposals'][0]['token'];key=uuid.uuid4()
        a=self.post('apply/',{'token':token},key);self.assertEqual(a.status_code,200,a.data)
        self.assertEqual(self.post('apply/',{'token':token},key).data,a.data)
        self.work.refresh_from_db();self.assertEqual(self.work.priority,'high');self.assertEqual(self.work.version,2)
        self.assertEqual(AuditEvent.objects.filter(action='ai_priority_approved').count(),1)
    @patch('core.ai.complete')
    def test_stale_version_blocks_apply(self,m):
        m.return_value=self.reply();r=self.ask();self.work.version+=1;self.work.save()
        self.assertEqual(self.post('apply/',{'token':r.data['proposals'][0]['token']}).status_code,409)
    @patch('core.ai.complete')
    def test_proposal_tampering_and_other_user(self,m):
        m.return_value=self.reply();r=self.ask();t=r.data['proposals'][0]['token']
        self.assertEqual(self.post('apply/',{'token':t+'tamper'}).status_code,400)
        self.client.force_login(self.admin);s=self.client.session;s['security_version']=1;s.save()
        self.assertEqual(self.post('apply/',{'token':t}).status_code,403)
    @patch('core.ai.complete')
    def test_retries_cached_and_counted_once(self,m):
        m.return_value=self.reply();c=self.client.get('/api/v1/ai/context/',{'org':str(self.org.pk)}).data
        data={'org':str(self.org.pk),'question':'Fråga','context_digest':c['digest']};key=uuid.uuid4()
        self.assertEqual(self.post('chat/',data,key).status_code,200);self.assertEqual(self.post('chat/',data,key).status_code,200)
        self.assertEqual(m.call_count,1);self.assertEqual(AIRequest.objects.count(),1)
        self.assertNotIn('Se arbetsorder',AIRequest.objects.get().encrypted_result)
    @patch('core.ai.complete')
    def test_revoked_access_during_call_withholds_answer(self,m):
        def revoke(*args):self.grant.active=False;self.grant.save();return self.reply()
        m.side_effect=revoke;self.assertEqual(self.ask().status_code,403);self.assertEqual(AIRequest.objects.get().state,'failed')
    @patch('core.ai.complete')
    def test_limit_disabled_and_stale_preview(self,m):
        m.return_value=self.reply();self.cfg.daily_limit=1;self.cfg.save()
        self.assertEqual(self.ask().status_code,200);self.assertEqual(self.ask().status_code,429)
        self.cfg.enabled=False;self.cfg.save();self.assertEqual(self.ask().status_code,400)
        self.cfg.enabled=True;self.cfg.save();self.assertEqual(self.ask(context_digest='old').status_code,409)
        self.assertEqual(m.call_count,1)
    @patch('core.ai.complete')
    def test_cross_branch_and_untrusted_proposals_rejected(self,m):
        self.assertEqual(self.client.get('/api/v1/ai/context/',{'org':str(self.other.pk)}).status_code,403)
        m.return_value={'answer':'Förslag','proposals':[{'id':['invalid'],'priority':'urgent'},{'id':str(self.secret.pk),'priority':'urgent'},{'id':str(self.work.pk),'priority':'execute_sql'}]}
        self.assertEqual(self.ask().data['proposals'],[])
    def test_settings_require_admin_stepup_encrypt_and_redact(self):
        self.assertEqual(self.client.get('/api/v1/ai/settings/').status_code,403)
        self.client.force_login(self.admin);s=self.client.session;s['security_version']=1;s.save()
        data={'version':1,'endpoint':'https://api.openai.com/v1','model':'test-model','api_key':'new-private-key','daily_limit':12,'organizations':[str(self.org.pk)],'enabled':True,'allow_changes':False,'password':'wrong'}
        self.assertEqual(self.post('settings/',data).status_code,403)
        data['password']='test-password-ai';r=self.post('settings/',data);self.assertEqual(r.status_code,200,r.data)
        self.cfg.refresh_from_db();self.assertNotIn('new-private-key',self.cfg.encrypted_api_key)
        self.assertNotIn('private-key',json.dumps(r.data));self.assertNotIn('private-key',str(list(AuditEvent.objects.values())))
        data.update(version=2,endpoint='https://other.example/v1',api_key='');self.assertEqual(self.post('settings/',data).status_code,400)
    def test_ssrf_and_https_guards(self):
        for url in ['http://127.0.0.1','https://user:pass@example.com','https://example.com?secret=x']:
            with self.assertRaises(ValidationError):resolved_address(url)
        with patch('core.ai.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValidationError):resolved_address('https://gateway.example')
            with override_settings(AI_PRIVATE_ORIGINS=['https://gateway.example']):self.assertEqual(resolved_address('https://gateway.example')[1],'127.0.0.1')
    @patch('core.ai.PinnedHTTPS')
    @patch('core.ai.resolved_address')
    def test_provider_protocol_no_redirects_or_secret_error(self,resolve,connection):
        from urllib.parse import urlsplit
        resolve.return_value=(urlsplit('https://api.openai.com/v1'),'1.1.1.1');response=connection.return_value.getresponse.return_value
        response.status=200;response.read.return_value=json.dumps({'choices':[{'message':{'content':json.dumps(self.reply())}}]}).encode()
        self.assertEqual(complete(self.cfg,'Q',{})['answer'],'Se arbetsorder #1.')
        args=connection.return_value.request.call_args.args;self.assertEqual(args[1],'/v1/chat/completions');self.assertEqual(args[3]['Authorization'],'Bearer provider-secret')
        response.status=302;response.read.return_value=b'provider-secret'
        with self.assertRaises(ValidationError) as e:complete(self.cfg,'Q',{})
        self.assertNotIn('provider-secret',str(e.exception))

    def test_bounded_context_preserves_full_status_totals(self):
        WorkOrder.objects.bulk_create([WorkOrder(org=self.org,asset=self.asset,number=i+10,title='Synthetic',status='planned') for i in range(105)])
        r=self.client.get('/api/v1/ai/context/',{'org':str(self.org.pk)})
        self.assertEqual(r.status_code,200,r.data);c=r.data['context']
        self.assertEqual(c['included'],100);self.assertEqual(c['total'],106)
        self.assertEqual(sum(x['count'] for x in c['status_counts']),106)
        self.assertEqual(next(x['count'] for x in c['status_counts'] if x['status']=='planned'),105)
