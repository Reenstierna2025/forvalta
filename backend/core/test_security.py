import uuid,time
from unittest.mock import patch
import pyotp
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from .models import *
from .security import state_for,issue_codes,code_digest
from .auth import cipher

@override_settings(DEBUG=True,SECURE_SSL_REDIRECT=False,MFA_REQUIRED=False)
class AccessTests(TestCase):
    def setUp(self):
        U=get_user_model();self.admin=U.objects.create_superuser('sys',password='example-security-password');self.other=U.objects.create_superuser('second',password='example-security-password');self.target=U.objects.create_user('target',password='example-security-password')
        self.root=OrgUnit.objects.create(name='Root',kind='church');self.a=OrgUnit.objects.create(name='A',kind='diocese',parent=self.root);self.b=OrgUnit.objects.create(name='B',kind='diocese',parent=self.root)
        self.grant=Membership.objects.create(user=self.target,org=self.a,role='worker')
        self.c=self.login(self.admin);self.victim=self.login(self.target)
    def login(self,user):
        c=APIClient();r=c.post('/api/v1/auth/',{'username':user.username,'password':'example-security-password'},format='json');self.assertEqual(r.status_code,200);return c
    def post(self,path,data,client=None):
        return (client or self.c).post('/api/v1/'+path,{**data,'password':'example-security-password'},format='json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    def test_revoke_grant_terminates_existing_session(self):
        r=self.post('access/reduce/',{'user':self.target.pk,'grant':self.grant.pk,'version':1,'action':'revoke_grant','reason':'Avslutat uppdrag i organisationen'})
        self.assertEqual(r.status_code,200,r.data);self.grant.refresh_from_db();self.assertFalse(self.grant.active)
        self.assertEqual(self.victim.get('/api/v1/work/').status_code,401)
        c=self.login(self.target);self.assertEqual(c.get('/api/v1/work/').data['count'],0)
        self.assertEqual(c.get('/api/v1/bootstrap/').data['grants'],[])
    def test_branch_admin_cannot_revoke_other_branch_or_close_account(self):
        branch=get_user_model().objects.create_user('branch',password='example-security-password');Membership.objects.create(user=branch,org=self.b,role='admin');c=self.login(branch)
        r=self.post('access/reduce/',{'user':self.target.pk,'grant':self.grant.pk,'version':1,'action':'revoke_grant','reason':'Kontroll av organisationsgräns'},c);self.assertEqual(r.status_code,403)
        r=self.post('access/reduce/',{'user':self.target.pk,'version':1,'action':'disable_account','reason':'Kontroll av organisationsgräns'},c);self.assertEqual(r.status_code,403)
    def test_disable_and_stale_version(self):
        r=self.post('access/reduce/',{'user':self.target.pk,'version':99,'action':'disable_account','reason':'Anställningen har avslutats'});self.assertEqual(r.status_code,409)
        r=self.post('access/reduce/',{'user':self.target.pk,'version':1,'action':'disable_account','reason':'Anställningen har avslutats'});self.assertEqual(r.status_code,200)
        self.assertEqual(self.victim.get('/api/v1/work/').status_code,401)
        self.assertEqual(APIClient().post('/api/v1/auth/',{'username':'target','password':'example-security-password'},format='json').status_code,400)
    def test_self_disable_denied(self):
        self.assertEqual(self.post('access/reduce/',{'user':self.admin.pk,'action':'disable_account','reason':'Självavstängning ska nekas','version':1}).status_code,400)
    def test_invalid_identity_is_validation_error(self):
        self.assertEqual(self.post('access/reduce/',{'user':'not-a-number'}).status_code,400)
    def test_admin_reset_needs_second_admin_and_no_secret_in_audit(self):
        r=self.post('access/resets/',{'user':self.target.pk,'reason':'Identitet kontrollerad via separat rutin'});self.assertEqual(r.status_code,201,r.data);id=r.data['id']
        self.assertEqual(self.post(f'access/resets/{id}/approve/',{'version':1}).status_code,403)
        r=self.post(f'access/resets/{id}/approve/',{'version':1},self.login(self.other));self.assertEqual(r.status_code,200,r.data)
        secret=r.data['recovery_code'];self.assertNotIn(secret,str(list(AuditEvent.objects.values())));self.assertNotIn(secret,str(list(MutationReceipt.objects.values())))
        self.assertEqual(self.victim.get('/api/v1/work/').status_code,401)
        self.assertEqual(self.post(f'access/resets/{id}/approve/',{'version':1},self.login(self.other)).status_code,409)
    def test_security_throttle_survives_rollback(self):
        for _ in range(11):r=self.c.post('/api/v1/security/',{'action':'revoke_sessions','password':'wrong'},format='json')
        self.assertEqual(r.status_code,429)
    @override_settings(MFA_REQUIRED=True)
    def test_recovery_codes_single_use_and_new_enrollment(self):
        c=APIClient();c.post('/api/v1/auth/',{'username':'target','password':'example-security-password'},format='json')
        secret=c.get('/api/v1/auth/mfa/').data['secret']
        r=c.post('/api/v1/auth/mfa/',{'code':pyotp.TOTP(secret).now()},format='json');self.assertEqual(r.status_code,200,r.data)
        codes=r.data['recovery_codes'];self.assertEqual(len(codes),10)
        self.assertNotIn(codes[0],str(list(RecoveryCode.objects.values())))
        c.delete('/api/v1/auth/');c.post('/api/v1/auth/',{'username':'target','password':'example-security-password'},format='json')
        r=c.post('/api/v1/auth/recover/',{'recovery_code':codes[0]},format='json');self.assertEqual(r.status_code,200,r.data)
        self.assertIsNone(c.get('/api/v1/auth/').data['user'])
        new=c.get('/api/v1/auth/mfa/').data['secret'];self.assertNotEqual(new,secret)
        r=c.post('/api/v1/auth/mfa/',{'code':pyotp.TOTP(new).now()},format='json');self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(RecoveryCode.objects.filter(user=self.target,used_at__isnull=True).count(),10)
        c.delete('/api/v1/auth/');c.post('/api/v1/auth/',{'username':'target','password':'example-security-password'},format='json')
        self.assertEqual(c.post('/api/v1/auth/recover/',{'recovery_code':codes[0]},format='json').status_code,400)
    @override_settings(MFA_REQUIRED=True)
    def test_revoked_preauth_cannot_complete_mfa(self):
        c=APIClient();c.post('/api/v1/auth/',{'username':'target','password':'example-security-password'},format='json')
        secret=c.get('/api/v1/auth/mfa/').data['secret'];state=state_for(self.target);state.version+=1;state.save()
        self.assertEqual(c.post('/api/v1/auth/mfa/',{'code':pyotp.TOTP(secret).now()},format='json').status_code,403)
    def test_grant_cannot_expand_beyond_administrators_explicit_scope(self):
        branch=get_user_model().objects.create_user('limited',password='example-security-password')
        Membership.objects.create(user=branch,org=self.root,role='admin',descendants=False,finance=True)
        c=self.login(branch)
        r=self.post('users/',{'org':str(self.root.pk),'username':'should-not-exist','role':'admin','descendants':True,'finance':True},c)
        self.assertEqual(r.status_code,403,r.data);self.assertFalse(get_user_model().objects.filter(username='should-not-exist').exists())
