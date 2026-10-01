import hashlib,io,json,uuid
from datetime import date,timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction,IntegrityError,DatabaseError
from django.test import TestCase,override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import *
from core.services import number,next_occurrence,generate_schedule
from core.reports import build_report
from core.management.commands.worker import process_job

@override_settings(SECURE_SSL_REDIRECT=False,MFA_REQUIRED=False)
class PlatformTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model();cls.admin=User.objects.create_user('admin',password='a-secure-test-password',email='admin@example.invalid');cls.worker=User.objects.create_user('worker');cls.vendor=User.objects.create_user('vendor');cls.reader=User.objects.create_user('reader')
        cls.root=OrgUnit.objects.create(name='Kyrkan',kind='church')
        cls.diocese=OrgUnit.objects.create(name='Stift A',kind='diocese',parent=cls.root)
        cls.pastorate=OrgUnit.objects.create(name='Pastorat A',kind='pastorate',parent=cls.diocese)
        cls.a=OrgUnit.objects.create(name='Församling A',kind='parish',parent=cls.pastorate)
        cls.b=OrgUnit.objects.create(name='Församling B',kind='parish',parent=cls.pastorate)
        Membership.objects.create(user=cls.admin,org=cls.a,role='admin',finance=True)
        Membership.objects.create(user=cls.worker,org=cls.a,role='worker')
        Membership.objects.create(user=cls.vendor,org=cls.a,role='contractor')
        Membership.objects.create(user=cls.reader,org=cls.a,role='reader')
        cls.asset=Asset.objects.create(org=cls.a,name='Fastighet A',kind='property',public=True)
        cls.other=Asset.objects.create(org=cls.b,name='HEMLIG FASTIGHET B',kind='property')
        cls.work=WorkOrder.objects.create(org=cls.a,asset=cls.asset,number=1,title='Uppdrag A',assigned_to=cls.vendor)
        cls.hidden=WorkOrder.objects.create(org=cls.b,asset=cls.other,number=2,title='HEMLIGT UPPDRAG B')
        cls.internal=WorkOrder.objects.create(org=cls.a,asset=cls.asset,number=3,title='Internt uppdrag')
        Counter.objects.create(name='work',value=3)
    def setUp(self):self.client=APIClient();self.client.force_authenticate(self.admin)
    def post(self,path,data,key=None):return self.client.post('/api/v1/'+path,data,format='json',HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()))
    def patch(self,path,data,key=None):return self.client.patch('/api/v1/'+path,data,format='json',HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()))
    def create_work(self,key=None):return self.post('work/',{'org':str(self.a.id),'asset':str(self.asset.id),'title':'Ny arbetsorder'},key)
    def test_organization_isolation_list_direct_search(self):
        for path in ['assets/','assets/?q=HEMLIG','work/','work/?q=HEMLIG','bootstrap/']:
            r=self.client.get('/api/v1/'+path);self.assertEqual(r.status_code,200);self.assertNotIn('HEMLIG',r.content.decode())
        self.assertEqual(self.client.get('/api/v1/work/'+str(self.hidden.id)+'/').status_code,404)
    def test_organization_isolation_report_export(self):
        for kind in ['work','assets','budget','energy','keys','registry','invoices']:
            r=self.client.get('/api/v1/reports/',{'type':kind});self.assertEqual(r.status_code,200);self.assertNotIn('HEMLIG',r.content.decode())
        r=self.client.get('/api/v1/reports/',{'type':'work','format_file':'csv'});self.assertNotIn('HEMLIG',r.content.decode())
    def test_cross_org_reference_rejected_atomically(self):
        count=WorkOrder.objects.count();r=self.post('work/',{'org':str(self.a.id),'asset':str(self.other.id),'title':'Fel relation'})
        self.assertEqual(r.status_code,400);self.assertEqual(count,WorkOrder.objects.count());self.assertEqual(MutationReceipt.objects.count(),0)
    def test_create_outside_scope_denied(self):
        r=self.post('assets/',{'org':str(self.b.id),'name':'Intrång','kind':'property'});self.assertEqual(r.status_code,403)
    def test_reader_cannot_write(self):
        self.client.force_authenticate(self.reader);self.assertEqual(self.create_work().status_code,403)
    def test_contractor_assigned_only_and_no_finance(self):
        self.client.force_authenticate(self.vendor);r=self.client.get('/api/v1/work/');self.assertEqual(r.data['count'],1)
        self.assertEqual(self.client.get('/api/v1/work/'+str(self.internal.id)+'/').status_code,404)
        self.assertEqual(self.client.get('/api/v1/reports/?type=budget').status_code,403)
        self.assertEqual(self.client.get('/api/v1/costs/').data['count'],0)
    def test_contractor_cannot_reassign_or_read_internal_comment(self):
        WorkComment.objects.create(work=self.work,text='Intern hemlighet',visibility='internal',author=self.admin)
        WorkComment.objects.create(work=self.work,text='Uppdragsinfo',visibility='contractor',author=self.admin)
        self.client.force_authenticate(self.vendor)
        self.assertEqual(self.patch('work/'+str(self.work.id)+'/',{'version':1,'title':'Egen rubrik'}).status_code,403)
        comments=self.client.get('/api/v1/work/'+str(self.work.id)+'/comments/');self.assertNotIn('Intern hemlighet',comments.content.decode());self.assertIn('Uppdragsinfo',comments.content.decode())
    def test_idempotent_create_and_fingerprint(self):
        key=uuid.uuid4();a=self.create_work(key);b=self.create_work(key);self.assertEqual(a.status_code,201);self.assertEqual(a.data,b.data);self.assertEqual(WorkOrder.objects.filter(title='Ny arbetsorder').count(),1)
        r=self.post('work/',{'org':str(self.a.id),'asset':str(self.asset.id),'title':'Annat'},key);self.assertEqual(r.status_code,409)
    def test_version_conflict_preserves_first_write(self):
        path='assets/'+str(self.asset.id)+'/'
        self.assertEqual(self.patch(path,{'version':1,'name':'Ändrat'}).status_code,200)
        self.assertEqual(self.patch(path,{'version':1,'name':'Förlorad uppdatering'}).status_code,409)
        self.asset.refresh_from_db();self.assertEqual(self.asset.name,'Ändrat');self.assertEqual(self.asset.version,2)
    def test_missing_idempotency_header_rejected(self):
        r=self.client.post('/api/v1/work/',{'title':'saknar nyckel'},format='json');self.assertEqual(r.status_code,400)
    def test_recover_receipt_is_user_scoped(self):
        key=uuid.uuid4();self.create_work(key);self.assertTrue(self.client.get('/api/v1/receipts/'+str(key)+'/').data['saved'])
        self.client.force_authenticate(self.worker);self.assertFalse(self.client.get('/api/v1/receipts/'+str(key)+'/').data['saved'])
    def test_checklist_required_for_completion(self):
        self.work.status='in_progress';self.work.checklist=['Kontroll A'];self.work.save()
        path='work/'+str(self.work.id)+'/transition/'
        self.assertEqual(self.post(path,{'version':1,'status':'completed'}).status_code,400)
        self.assertEqual(self.patch('work/'+str(self.work.id)+'/',{'version':1,'checklist_results':{'0':'ok'}}).status_code,200)
        self.assertEqual(self.post(path,{'version':2,'status':'completed'}).status_code,200)
    def test_invalid_transition_and_contractor_verification(self):
        self.assertEqual(self.post('work/'+str(self.work.id)+'/transition/',{'version':1,'status':'verified'}).status_code,400)
        self.work.status='completed';self.work.save();self.client.force_authenticate(self.vendor)
        self.assertEqual(self.post('work/'+str(self.work.id)+'/transition/',{'version':1,'status':'verified'}).status_code,403)
    def test_month_end_and_leap_year_anchoring(self):
        s=Schedule(asset=self.asset,org=self.a,title='Månadsrond',anchor_date=date(2024,1,31),next_date=date(2024,1,31),unit='month',interval=1)
        self.assertEqual(next_occurrence(s,date(2024,1,31)),date(2024,2,29));self.assertEqual(next_occurrence(s,date(2024,2,29)),date(2024,3,31))
        s.anchor_date=date(2024,2,29);s.unit='year';self.assertEqual(next_occurrence(s,date(2027,2,28)),date(2028,2,29))
    def test_dst_dates_and_schedule_duplicates(self):
        s=Schedule.objects.create(org=self.a,asset=self.asset,title='Daglig',anchor_date=date(2026,3,28),next_date=date(2026,3,28),unit='day',interval=1,checklist=['A'])
        self.assertEqual(generate_schedule(s.id,date(2026,3,30)),3);self.assertEqual(generate_schedule(s.id,date(2026,3,30)),0)
        self.assertEqual(WorkOrder.objects.filter(schedule=s).count(),3)
    def maintenance(self):return Maintenance.objects.create(org=self.a,asset=self.asset,title='Tak',year=2026,price_year=2026,quantity=3,unit_price=Decimal('19.99'),cost_factor=Decimal('1.25'),index_percent=2,interval_years=1)
    def test_decimal_budget_and_no_double_count(self):
        p=self.maintenance();self.assertEqual(p.budget_for(),Decimal('74.96'));self.assertEqual(p.budget_for(2027),Decimal('76.46'))
        Membership.objects.create(user=self.admin,org=self.root,role='admin',descendants=True,finance=True)
        r=build_report(self.admin,'budget',{'start_year':2026,'years':2});self.assertEqual(r['totals']['Budget'],'151.42');self.assertEqual(len(r['rows']),2)
    def test_scenario_isolation_and_publish_lock(self):
        p=self.maintenance();r=self.post('scenarios/',{'org':str(self.a.id),'name':'Scenario','start_year':2026,'years':5});self.assertEqual(r.status_code,201,r.data)
        id=r.data['id'];r=self.post('scenarios/'+id+'/revise/',{'version':1,'line':0,'year':2027});self.assertEqual(r.status_code,200,r.data);p.refresh_from_db();self.assertEqual(p.year,2026)
        self.assertEqual(self.post('scenarios/'+id+'/publish/',{'version':2}).status_code,200)
        self.assertEqual(self.post('scenarios/'+id+'/revise/',{'version':3,'line':0,'year':2028}).status_code,409)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():BudgetScenario.objects.filter(pk=id).update(name='Bypass')
    def test_audit_is_database_immutable(self):
        self.create_work();event=AuditEvent.objects.first()
        with self.assertRaises(DatabaseError):
            with transaction.atomic():AuditEvent.objects.filter(pk=event.pk).update(action='fabricated')
    def test_public_locations_and_private_feedback(self):
        self.client.force_authenticate(None)
        self.assertEqual(len(self.client.get('/api/v1/public/assets/').data),1)
        key=uuid.uuid4();data={'asset':str(self.asset.id),'title':'Publikt fel','description':'Trasigt'}
        a=self.post('public/issues/',data,key);b=self.post('public/issues/',data,key)
        self.assertEqual(a.status_code,201,a.data);self.assertEqual(a.data,b.data)
        w=WorkOrder.objects.get(number=a.data['number']);WorkComment.objects.create(work=w,text='Hemligt',visibility='internal');WorkComment.objects.create(work=w,text='Åtgärdat',visibility='public')
        r=self.post('public/track/',{'token':a.data['token']});self.assertEqual(r.status_code,200);self.assertNotIn('Hemligt',r.content.decode());self.assertIn('Åtgärdat',r.content.decode());self.assertNotIn('reporter_email',r.data)
        self.assertEqual(self.post('public/track/',{'token':'x'*64}).status_code,404)
    def test_no_public_submission_to_private_asset(self):
        self.client.force_authenticate(None);r=self.post('public/issues/',{'asset':str(self.other.id),'title':'Intrång'});self.assertEqual(r.status_code,404)
    def test_key_loan_unique_and_idempotent_return(self):
        k=Key.objects.create(org=self.a,asset=self.asset,name='Nyckel',system='A',serial='1');payload={'org':str(self.a.id),'key':str(k.id),'borrower':'A','due_date':'2099-01-01'}
        first=self.post('loans/',payload);self.assertEqual(first.status_code,201,first.data)
        self.assertEqual(self.post('loans/',payload).status_code,409)
        key=uuid.uuid4();path='loans/'+first.data['id']+'/return_key/';r=self.post(path,{'version':1},key);self.assertEqual(r.status_code,200);self.assertEqual(self.post(path,{'version':1},key).status_code,200)
    def test_meter_change_correct_consumption(self):
        m=Meter.objects.create(org=self.a,asset=self.asset,name='El',medium='electricity',unit='kWh')
        Reading.objects.create(org=self.a,meter=m,date=date(2026,1,1),value=100)
        bad=self.post('readings/',{'org':str(self.a.id),'meter':str(m.id),'date':'2026-02-01','value':5});self.assertEqual(bad.status_code,400)
        good=self.post('readings/',{'org':str(self.a.id),'meter':str(m.id),'date':'2026-02-01','value':5,'replacement':True,'old_final':120,'new_initial':0,'serial':'NEW'});self.assertEqual(good.status_code,201,good.data)
        r=build_report(self.admin,'energy',{});self.assertEqual(r['rows'][0]['Förbrukning'],None);self.assertEqual(Decimal(r['rows'][1]['Förbrukning']),25)
    def test_report_snapshot_rechecks_access_after_revocation(self):
        self.maintenance();r=self.post('reports/',{'type':'budget','filters':{'org':str(self.a.id),'start_year':2026,'years':1}});self.assertEqual(r.status_code,201,r.data)
        Membership.objects.filter(user=self.admin).update(finance=False)
        self.assertEqual(self.client.get('/api/v1/snapshots/'+r.data['id']+'/').status_code,404)
    def test_scheduled_report_rechecks_recipient_access(self):
        sub=Subscription.objects.create(org=self.a,name='Budget',report_type='budget',config={'org':str(self.a.id)},recipient=self.admin,next_date=date(2026,1,1))
        Membership.objects.filter(user=self.admin).update(finance=False)
        job=Job.objects.create(kind='report_email',payload={'subscription':str(sub.id)},dedupe_key='test',run_after=timezone.now())
        with self.assertRaises(PermissionError):process_job(job)
        self.assertEqual(ReportSnapshot.objects.count(),0)
    def test_report_csv_formula_injection_and_missing_value(self):
        self.asset.name='=HYPERLINK("evil")';self.asset.save()
        r=self.client.get('/api/v1/reports/?type=assets&format_file=csv');self.assertIn("'=HYPERLINK",r.content.decode());self.assertIn('Saknas',r.content.decode())
    def test_export_formats(self):
        for fmt in ['pdf','xlsx']:
            r=self.client.get('/api/v1/reports/',{'type':'work','format_file':fmt});self.assertEqual(r.status_code,200);data=b''.join(r.streaming_content);self.assertTrue(data.startswith(b'%PDF') if fmt=='pdf' else data.startswith(b'PK'))
    def test_documents_are_not_public_and_scope_enforced(self):
        d=Document.objects.create(org=self.b,asset=self.other,title='Hemlig fil',file_key='none',sha256='0'*64,size=1,mime='application/pdf')
        self.assertEqual(self.client.get('/api/v1/documents/'+str(d.id)+'/download/').status_code,404)
    def test_untrusted_file_rejected_before_storage(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f=SimpleUploadedFile('bad.html',b'<script>evil</script>',content_type='text/html')
        r=self.client.post('/api/v1/documents/',{'asset':str(self.asset.id),'file':f},format='multipart',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()));self.assertEqual(r.status_code,400);self.assertEqual(Document.objects.count(),0)
    def test_csrf_login_required(self):
        c=APIClient(enforce_csrf_checks=True)
        self.assertEqual(c.post('/api/v1/auth/',{'username':'admin','password':'a-secure-test-password'},format='json').status_code,403)
        r=c.get('/api/v1/auth/');r=c.post('/api/v1/auth/',{'username':'admin','password':'a-secure-test-password'},format='json',HTTP_X_CSRFTOKEN=r.data['csrf']);self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(c.get('/api/v1/auth/').data['user']['username'],'admin')
    @override_settings(MFA_REQUIRED=True,DEBUG=True)
    def test_mfa_enrollment_and_replay(self):
        import pyotp
        c=APIClient();r=c.post('/api/v1/auth/',{'username':'admin','password':'a-secure-test-password'},format='json');self.assertTrue(r.data['mfa'])
        self.assertIsNone(c.get('/api/v1/auth/').data['user'])
        secret=c.get('/api/v1/auth/mfa/').data['secret'];code=pyotp.TOTP(secret).now()
        self.assertEqual(c.post('/api/v1/auth/mfa/',{'code':code},format='json').status_code,200)
        c.delete('/api/v1/auth/');c.post('/api/v1/auth/',{'username':'admin','password':'a-secure-test-password'},format='json')
        self.assertEqual(c.post('/api/v1/auth/mfa/',{'code':code},format='json').status_code,400)
    def test_hierarchy_and_move_prevention(self):
        r=self.post('organizations/',{'name':'Fel','kind':'diocese','parent':str(self.a.id)});self.assertEqual(r.status_code,400)
        r=self.patch('organizations/'+str(self.a.id)+'/',{'version':1,'parent':str(self.root.id)});self.assertEqual(r.status_code,400)
    def test_report_retry_reuses_immutable_snapshot(self):
        from unittest.mock import patch
        sub=Subscription.objects.create(org=self.a,name='Arbetsrapport',report_type='work',config={'org':str(self.a.id)},recipient=self.admin,next_date=date.today())
        job=Job.objects.create(kind='report_email',payload={'subscription':str(sub.id)},dedupe_key='retry-snapshot',run_after=timezone.now())
        with patch('core.management.commands.worker.send_mail',side_effect=OSError('SMTP disconnected')):
            with self.assertRaises(OSError):process_job(job)
        with patch('core.management.commands.worker.send_mail'):
            process_job(Job.objects.get(pk=job.pk))
        self.assertEqual(ReportSnapshot.objects.count(),1)

@override_settings(SECURE_SSL_REDIRECT=False,MFA_REQUIRED=False)
class InspectionTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('inspector')
        self.org=OrgUnit.objects.create(name='Test A',kind='parish')
        self.other=OrgUnit.objects.create(name='Test B',kind='parish')
        Membership.objects.create(user=self.user,org=self.org,role='admin')
        self.asset=Asset.objects.create(org=self.org,name='Testbyggnad',kind='property')
        self.client=APIClient();self.client.force_authenticate(self.user)
    def send(self,path,data,method='post',key=None):
        return getattr(self.client,method)('/api/v1/'+path,data,format='json',HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()))
    def planned(self):
        r=self.send('inspections/',{'asset':str(self.asset.pk),'title':'Syntetisk kontroll','template':'sba','scheduled_date':'2026-10-01'})
        self.assertEqual(r.status_code,201,r.data)
        return Inspection.objects.get(pk=r.data['id'])
    def publish(self,obj,fail=False):
        answers={x['key']:{'result':'fail' if fail and i==0 else 'pass','note':'Blockerad väg' if fail and i==0 else '', 'documents':[]} for i,x in enumerate(obj.items)}
        r=self.send(f'inspections/{obj.pk}/',{'version':obj.version,'answers':answers},'patch');self.assertEqual(r.status_code,200,r.data)
        obj.refresh_from_db();r=self.send(f'inspections/{obj.pk}/publish/',{'version':obj.version});self.assertEqual(r.status_code,200,r.data);obj.refresh_from_db()
    def test_complete_followup_chain_and_idempotent_order(self):
        obj=self.planned();self.publish(obj,True);f=InspectionFinding.objects.get()
        data={'version':f.version,'assigned_to':self.user.pk,'due_date':'2026-10-02','priority':'normal'};key=uuid.uuid4()
        a=self.send(f'findings/{f.pk}/order/',data,key=key);b=self.send(f'findings/{f.pk}/order/',data,key=key)
        self.assertEqual(a.status_code,201,a.data);self.assertEqual(a.data,b.data);self.assertEqual(WorkOrder.objects.count(),1)
        r=self.send(f'inspections/{obj.pk}/followup/',{'version':obj.version,'mode':'followup','reason':'Kontroll av åtgärd','scheduled_date':'2026-10-02'})
        self.assertEqual(r.status_code,201,r.data);follow=Inspection.objects.get(pk=r.data['id']);self.publish(follow)
        f.refresh_from_db();data={'version':f.version,'inspection':str(follow.pk)}
        self.assertEqual(self.send(f'findings/{f.pk}/verify/',data).status_code,400)
        WorkOrder.objects.filter(pk=a.data['id']).update(status='completed')
        self.assertEqual(self.send(f'findings/{f.pk}/verify/',data).status_code,200)
        f.refresh_from_db();self.assertEqual(f.state,'verified');self.assertEqual(f.verification_id,follow.pk)
        pdf=self.client.get(f'/api/v1/inspections/{obj.pk}/protocol/');self.assertEqual(pdf.status_code,200);self.assertTrue(b''.join(pdf.streaming_content).startswith(b'%PDF'))
    def test_published_immutable_in_api_and_database_and_correction(self):
        obj=self.planned();self.publish(obj)
        r=self.send(f'inspections/{obj.pk}/',{'version':obj.version,'answers':{}},'patch');self.assertEqual(r.status_code,409)
        with self.assertRaises(DatabaseError),transaction.atomic():Inspection.objects.filter(pk=obj.pk).update(title='Manipulerat')
        r=self.send(f'inspections/{obj.pk}/followup/',{'version':obj.version,'mode':'correction','reason':'Förtydliga anteckning','scheduled_date':'2026-10-01'})
        self.assertEqual(r.status_code,201,r.data);revision=Inspection.objects.get(pk=r.data['id']);self.assertEqual(revision.supersedes_id,obj.pk);self.assertEqual(revision.answers,obj.answers)
        obj.refresh_from_db();self.assertEqual(obj.title,'Syntetisk kontroll')
    def test_incomplete_and_stale_writes_rejected(self):
        obj=self.planned();self.assertEqual(self.send(f'inspections/{obj.pk}/publish/',{'version':1}).status_code,400)
        self.assertEqual(self.send(f'inspections/{obj.pk}/',{'version':1,'answers':{}},'patch').status_code,200)
        self.assertEqual(self.send(f'inspections/{obj.pk}/',{'version':1,'answers':{}},'patch').status_code,409)
        self.assertEqual(InspectionFinding.objects.count(),0)
    def test_scope_and_document_relationship(self):
        obj=self.planned();otherasset=Asset.objects.create(org=self.other,name='Hemlig',kind='property')
        hidden=Inspection.objects.create(org=self.other,asset=otherasset,title='Hemlig',scheduled_date=date.today(),items=[])
        self.assertEqual(self.client.get(f'/api/v1/inspections/{hidden.pk}/').status_code,404)
        r=self.send('inspections/',{'asset':str(otherasset.pk),'title':'Försök','template':'sba','scheduled_date':'2026-10-01'});self.assertEqual(r.status_code,403)
        bad={obj.items[0]['key']:{'result':'pass','documents':[str(uuid.uuid4())]}}
        self.assertEqual(self.send(f'inspections/{obj.pk}/',{'version':1,'answers':bad},'patch').status_code,400)
        member=Membership.objects.get(user=self.user);member.role='reader';member.save()
        self.assertEqual(self.send(f'inspections/{obj.pk}/publish/',{'version':1}).status_code,403)
    def test_reopened_finding_requires_new_work_and_latest_reinspection(self):
        obj=self.planned();self.publish(obj,True);f=InspectionFinding.objects.get()
        def follow(source):
            r=self.send(f'inspections/{source.pk}/followup/',{'version':source.version,'mode':'followup','reason':'Ny kontroll av åtgärd','scheduled_date':'2026-10-02'})
            self.assertEqual(r.status_code,201,r.data);return Inspection.objects.get(pk=r.data['id'])
        good=follow(obj);self.publish(good)
        self.assertEqual(self.send(f'findings/{f.pk}/verify/',{'version':f.version,'inspection':str(good.pk)}).status_code,200)
        bad=follow(good);self.publish(bad,True);f.refresh_from_db()
        self.assertEqual(f.state,'open');self.assertIsNone(f.verification);self.assertIsNone(f.work);self.assertEqual(f.inspection_id,bad.pk)
        self.assertEqual(self.send(f'findings/{f.pk}/verify/',{'version':f.version,'inspection':str(good.pk)}).status_code,400)
        newer=follow(bad);self.publish(newer)
        r=self.send(f'inspections/{newer.pk}/followup/',{'version':newer.version,'mode':'correction','reason':'Rättelse av ombesiktning','scheduled_date':'2026-10-02'})
        correction=Inspection.objects.get(pk=r.data['id']);self.publish(correction)
        self.assertEqual(self.send(f'findings/{f.pk}/verify/',{'version':f.version,'inspection':str(newer.pk)}).status_code,409)
        self.assertEqual(self.send(f'findings/{f.pk}/verify/',{'version':f.version,'inspection':str(correction.pk)}).status_code,200)
    def test_overview_and_mutations_respect_scope(self):
        obj=self.planned();self.publish(obj,True)
        hiddenasset=Asset.objects.create(org=self.other,name='Hemlig',kind='property')
        hidden=Inspection.objects.create(org=self.other,asset=hiddenasset,title='Hemlig',scheduled_date=date.today(),items=[])
        for suffix in ['publish/','followup/']:
            self.assertEqual(self.send(f'inspections/{hidden.pk}/{suffix}',{'version':1}).status_code,404)
        overview=self.client.get('/api/v1/inspections/overview/');self.assertEqual(overview.status_code,200);self.assertEqual(overview.data['open_findings'],1);self.assertEqual(overview.data['planned'],0)
        self.client.force_authenticate(get_user_model().objects.create_user('outsider'))
        self.assertEqual(self.client.get('/api/v1/inspections/overview/').data['open_findings'],0)


@override_settings(SECURE_SSL_REDIRECT=False)
class ReadinessTests(TestCase):
    def test_database_readiness(self):
        self.assertEqual(self.client.get('/api/health/').status_code,200)
    def test_database_failure_is_unhealthy_without_details(self):
        from unittest.mock import patch
        from django.db import OperationalError
        with patch('core.health.connection.cursor',side_effect=OperationalError('private connection information')):
            response=self.client.get('/api/health/')
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private connection information',response.content.decode())

@override_settings(DEBUG=False,S3_BUCKET='',LOCAL_DOCUMENT_STORAGE=True)
class PilotStorageTests(TestCase):
    def test_private_local_document_survives_reopen_and_detects_corruption(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from core.storage import put_file,read_file
        from rest_framework.exceptions import ValidationError
        data=b'%PDF-1.4 synthetic pilot document'
        with tempfile.TemporaryDirectory() as directory,override_settings(MEDIA_ROOT=Path(directory)):
            key=put_file(data)
            doc=SimpleNamespace(file_key=key,sha256=hashlib.sha256(data).hexdigest())
            self.assertEqual(read_file(doc),data)
            (Path(directory)/key).write_bytes(b'changed')
            with self.assertRaises(ValidationError):read_file(doc)

    @override_settings(LOCAL_DOCUMENT_STORAGE=False)
    def test_production_does_not_implicitly_enable_local_storage(self):
        from core.storage import put_file
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):put_file(b'test')

    @override_settings(FILE_SCAN_COMMAND='')
    def test_pilot_still_requires_upload_scanning(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.storage import inspect_upload
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):inspect_upload(SimpleUploadedFile('test.pdf',b'%PDF-1.4 synthetic'))
