from concurrent.futures import ThreadPoolExecutor
import uuid
from unittest import skipUnless
from django.db import connection,connections,close_old_connections
from django.test import TransactionTestCase,override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import OrgUnit,Membership,Asset,WorkOrder

@skipUnless(connection.vendor=='postgresql','Real concurrent writes require PostgreSQL')
@override_settings(SECURE_SSL_REDIRECT=False,MFA_REQUIRED=False)
class ConcurrentWrites(TransactionTestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('race')
        self.org=OrgUnit.objects.create(name='Kyrkan',kind='church')
        Membership.objects.create(user=self.user,org=self.org,role='admin',finance=True)
        self.asset=Asset.objects.create(org=self.org,name='Test',kind='property')
    def request(self,method,path,data,key):
        close_old_connections()
        try:
            c=APIClient();c.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
            r=getattr(c,method)('/api/v1/'+path,data,format='json',HTTP_IDEMPOTENCY_KEY=key)
            return r.status_code,dict(r.data)
        finally:connections.close_all()
    def test_concurrent_retries_create_exactly_one_work(self):
        key=str(uuid.uuid4());data={'org':str(self.org.id),'asset':str(self.asset.id),'title':'Samma begäran'}
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.request('post','work/',data,key),range(2)))
        self.assertEqual([r[0] for r in results],[201,201]);self.assertEqual(results[0][1],results[1][1]);self.assertEqual(WorkOrder.objects.count(),1)
    def test_concurrent_versions_preserve_one_winner(self):
        path='assets/'+str(self.asset.id)+'/'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda i:self.request('patch',path,{'version':1,'name':f'Försök {i}'},str(uuid.uuid4())),range(2)))
        self.assertEqual(sorted(r[0] for r in results),[200,409]);self.asset.refresh_from_db();self.assertEqual(self.asset.version,2)
    def test_full_export_requires_system_admin_and_excludes_credentials(self):
        import io,zipfile,json
        c=APIClient();c.force_authenticate(self.user)
        self.assertEqual(c.get('/api/v1/full-export/').status_code,403)
        self.user.is_superuser=True;self.user.save()
        r=c.get('/api/v1/full-export/');self.assertEqual(r.status_code,200)
        with zipfile.ZipFile(io.BytesIO(b''.join(r.streaming_content))) as z:
            self.assertIn('manifest.json',z.namelist());self.assertIn('data/asset.json',z.namelist())
            users=json.loads(z.read('data/users.json'));self.assertNotIn('password',users[0])
            self.assertNotIn('data/mfaprofile.json',z.namelist())
    @override_settings(DEBUG=True,MFA_REQUIRED=True)
    def test_recovery_code_concurrent_redemption_has_one_winner(self):
        from core.security import issue_codes
        from core.auth import cipher
        from core.models import MFAProfile,RecoveryCode
        import pyotp
        self.user.set_password('concurrent-recovery-password');self.user.save()
        MFAProfile.objects.create(user=self.user,enabled=True,encrypted_secret=cipher().encrypt(pyotp.random_base32().encode()).decode())
        codes=issue_codes(self.user)
        clients=[]
        for _ in range(2):
            c=APIClient();r=c.post('/api/v1/auth/',{'username':self.user.username,'password':'concurrent-recovery-password'},format='json');self.assertEqual(r.status_code,200);clients.append(c)
        def redeem(c):
            close_old_connections()
            try:return c.post('/api/v1/auth/recover/',{'recovery_code':codes[0]},format='json').status_code
            finally:connections.close_all()
        with ThreadPoolExecutor(2) as pool:statuses=list(pool.map(redeem,clients))
        self.assertEqual(statuses.count(200),1);self.assertTrue(all(s in [200,400,403] for s in statuses))
        self.assertEqual(RecoveryCode.objects.filter(user=self.user,used_at__isnull=False).count(),1)
    @override_settings(DEBUG=True)
    def test_ai_concurrent_daily_limit_reserves_one_call(self):
        from unittest.mock import patch
        from core.models import AIConfiguration,AIRequest
        from core.ai import make_context,digest
        from core.auth import cipher
        c=AIConfiguration.objects.create(enabled=True,model='test',daily_limit=1,encrypted_api_key=cipher().encrypt(b'test').decode());c.organizations.add(self.org)
        data={'org':str(self.org.pk),'question':'Summera','context_digest':digest(make_context(self.user,self.org.pk,c))}
        with patch('core.ai.complete',return_value={'answer':'Inga arbetsorder.','proposals':[]}) as complete:
            with ThreadPoolExecutor(2) as pool:
                results=list(pool.map(lambda _:self.request('post','ai/chat/',data,str(uuid.uuid4())),range(2)))
        self.assertEqual(sorted(r[0] for r in results),[200,429]);self.assertEqual(complete.call_count,1);self.assertEqual(AIRequest.objects.count(),1)
