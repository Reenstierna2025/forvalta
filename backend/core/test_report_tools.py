import uuid,copy
from decimal import Decimal
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from .models import OrgUnit,Membership,Asset,WorkOrder,Maintenance,BudgetScenario
from .reports import build_report
from .report_analysis import aggregate
from .scenario_compare import compare_scenarios

@override_settings(DEBUG=True,SECURE_SSL_REDIRECT=False,MFA_REQUIRED=False)
class ReportToolsTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('analyst');self.org=OrgUnit.objects.create(name='A',kind='church');self.other=OrgUnit.objects.create(name='B',kind='church')
        self.grant=Membership.objects.create(user=self.user,org=self.org,role='manager',finance=True)
        self.asset=Asset.objects.create(org=self.org,name='Hus',kind='property')
        WorkOrder.objects.create(org=self.org,asset=self.asset,number=1,title='Arbete',status='new')
        other=Asset.objects.create(org=self.other,name='Hemligt',kind='property');WorkOrder.objects.create(org=self.other,asset=other,number=2,title='Hemligt')
        Maintenance.objects.create(org=self.org,asset=self.asset,title='Tak',year=2026,interval_years=1,quantity=Decimal('.01'),unit_price=Decimal('.50'),cost_factor=1,price_year=2026)
        self.client=APIClient();self.client.force_authenticate(self.user)
    def make(self,name='Bas',lines=None,org=None):
        rows=lines if lines is not None else build_report(self.user,'budget',{'start_year':2026,'years':5})['rows']
        for row in rows:row.setdefault('line_key',str(row['id'])+':'+str(row['År']))
        return BudgetScenario.objects.create(org=org or self.org,name=name,start_year=2026,years=5,lines=rows,org_snapshot=[{'id':str((org or self.org).pk)}])
    def post(self,path,data,key=None):return self.client.post('/api/v1/'+path,data,format='json',HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()))
    def test_group_totals_and_drilldown_match_scoped_rows(self):
        r=build_report(self.user,'budget',{'start_year':2026,'years':5,'group_by':'Objekt','measure':'Budget'})
        self.assertEqual(r['rows'][0]['Värde'],'0.05');self.assertEqual(len(r['detail_rows']),5)
        self.assertEqual(r['analysis']['members']['0'],list(range(5)))
        work=build_report(self.user,'work',{'group_by':'Status','measure':'Antal'});self.assertEqual(work['rows'][0]['Värde'],'1');self.assertNotIn('Hemligt',str(work))
    def test_allowlist_and_missing_values(self):
        with self.assertRaises(ValidationError):aggregate('energy',[],{'group_by':'Enhet','measure':'Förbrukning'})
        with self.assertRaises(ValidationError):aggregate('work',[],{'group_by':'__class__'})
        r=aggregate('budget',[{'Objekt':None,'Budget':None},{'Objekt':'Saknas','Budget':'0.00'}],{'group_by':'Objekt','measure':'Budget'})
        self.assertEqual(len(r['groups']),2);self.assertEqual(next(x for x in r['groups'] if x['Grupp'] is None)['Värde'],None)
    def test_clone_then_move_preserves_identity_and_original(self):
        a=self.make();a.state='published';a.save();key=uuid.uuid4()
        data={'name':'Alternativ','version':1};r=self.post(f'scenarios/{a.pk}/clone/',data,key);self.assertEqual(r.status_code,201,r.data)
        self.assertEqual(self.post(f'scenarios/{a.pk}/clone/',data,key).data,r.data)
        b=BudgetScenario.objects.get(pk=r.data['id']);self.assertEqual(b.state,'draft')
        self.assertEqual(self.post(f'scenarios/{b.pk}/revise/',{'version':1,'line':0,'year':2028}).status_code,200)
        b.refresh_from_db();a.refresh_from_db();result=compare_scenarios(a,b)
        self.assertEqual(a.lines[0]['År'],2026);self.assertEqual(len(result['rows']),5)
        changed=[x for x in result['rows'] if x['Förändring']=='Ändrad'];self.assertEqual(len(changed),1);self.assertEqual(changed[0]['År efter'],2028)
        self.assertEqual(result['totals']['Skillnad'],'0.00')
        self.assertEqual(result['per_year'][0]['difference'],'-0.01');self.assertEqual(result['per_year'][2]['difference'],'0.01')
    def test_comparison_price_funding_and_added_removed_rows(self):
        a=self.make();rows=copy.deepcopy(a.lines);rows[0]['À-pris']='1.50';rows[0]['Budget']='0.02';rows[0]['Beviljad finansiering']='0.01';rows.pop();rows.append({**copy.deepcopy(rows[1]),'line_key':'new','Budget':'1.00'})
        b=self.make('Efter',rows);r=compare_scenarios(a,b)
        self.assertEqual(Decimal(r['totals']['Skillnad']),Decimal('1.00'))
        self.assertEqual({x['Förändring'] for x in r['rows']},{'Tillagd','Borttagen','Ändrad','Oförändrad'})
        changed=next(x for x in r['rows'] if x['Förändring']=='Ändrad');self.assertEqual(changed['À-pris efter'],'1.50');self.assertIn('Beviljad finansiering',changed['Ändrade fält'])
    def test_scope_finance_and_period_mismatch(self):
        a=self.make();b=self.make('Hemlig',org=self.other)
        self.assertEqual(self.client.get(f'/api/v1/scenarios/{a.pk}/compare/',{'other':str(b.pk)}).status_code,404)
        self.grant.finance=False;self.grant.save();self.assertEqual(self.client.get(f'/api/v1/scenarios/{a.pk}/compare/',{'other':str(a.pk)}).status_code,404)
        b.org=self.org;b.org_snapshot=a.org_snapshot;b.years=10
        with self.assertRaises(ValidationError):compare_scenarios(a,b)
    def test_grouped_exports_and_comparison_export(self):
        r=self.client.get('/api/v1/reports/',{'type':'work','group_by':'Status','format_file':'csv'});self.assertEqual(r.status_code,200)
        body=r.content if not r.streaming else b''.join(r.streaming_content);self.assertIn('Grupp',body.decode('utf-8-sig'))
        a=self.make();b=self.make('Alternativ');r=self.client.get(f'/api/v1/scenarios/{a.pk}/compare/',{'other':str(b.pk),'format_file':'xlsx'});self.assertEqual(r.status_code,200);self.assertTrue(b''.join(r.streaming_content).startswith(b'PK'))
    def test_export_rejects_changed_versions_and_keeps_numbers_numeric(self):
        import io
        from openpyxl import load_workbook
        a=self.make();lines=copy.deepcopy(a.lines);lines[0]['Budget']='0.00';b=self.make('Minskad',lines)
        base=f'/api/v1/scenarios/{a.pk}/compare/'
        self.assertEqual(self.client.get(base,{'other':str(b.pk),'format_file':'xlsx','before_version':99}).status_code,409)
        r=self.client.get(base,{'other':str(b.pk),'format_file':'xlsx','before_version':1,'after_version':1})
        wb=load_workbook(io.BytesIO(b''.join(r.streaming_content)));rows=list(wb.active.values);index=rows[0].index('Skillnad SEK')
        self.assertEqual(rows[1][index],-0.01);self.assertIsInstance(rows[1][index],float)
