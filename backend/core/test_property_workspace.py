from datetime import timedelta
from decimal import Decimal
from django.test import TestCase,override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from .models import OrgUnit,Membership,Asset,WorkOrder,CostEntry,Document,Maintenance,AuditEvent

@override_settings(SECURE_SSL_REDIRECT=False,MFA_REQUIRED=False)
class PropertyWorkspaceTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('property-manager');self.org=OrgUnit.objects.create(name='A',kind='church');self.other=OrgUnit.objects.create(name='B',kind='church')
        self.grant=Membership.objects.create(user=self.user,org=self.org,role='manager',finance=True)
        self.root=Asset.objects.create(org=self.org,name='Fastighet',kind='property',area=0)
        self.child=Asset.objects.create(org=self.org,parent=self.root,name='Byggnad',kind='building')
        self.room=Asset.objects.create(org=self.org,parent=self.child,name='Rum',kind='room')
        self.foreign=Asset.objects.create(org=self.other,name='Hemlig',kind='property')
        today=timezone.localdate()
        self.work=WorkOrder.objects.create(org=self.org,asset=self.room,title='Kontroll',number=1,status='completed',due_date=today-timedelta(days=1))
        self.cost=CostEntry.objects.create(org=self.org,work=self.work,kind='material',description='Belopp',quantity=Decimal('.01'),unit_price=Decimal('.50'),date=today)
        CostEntry.objects.create(org=self.org,work=self.work,kind='material',description='Belopp 2',quantity=Decimal('.01'),unit_price=Decimal('.50'),date=today)
        self.maintenance=Maintenance.objects.create(org=self.org,asset=self.child,title='Tak',year=today.year,price_year=today.year,quantity=1,unit_price=100)
        AuditEvent.objects.create(org=self.org,actor=self.user,entity='asset',entity_id=str(self.room.pk),action='created',after={'private':'not exposed'})
        AuditEvent.objects.create(org=self.org,actor=self.user,entity='costentry',entity_id=str(self.cost.pk),action='created')
        self.client=APIClient();self.client.force_authenticate(self.user)
    def get(self,section='summary',**params):return self.client.get(f'/api/v1/assets/{self.root.pk}/workspace/',{'section':section,**params})
    def test_nested_scope_and_line_rounding(self):
        r=self.get();self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data['counts']['objects'],2);self.assertEqual(r.data['counts']['overdue'],1);self.assertEqual(r.data['counts']['awaiting_verification'],1)
        self.assertEqual(r.data['costs']['amount'],'0.02');self.assertEqual(r.data['asset']['area'],'0.00')
        r=self.get('work',status='completed');self.assertEqual(r.data['count'],1);self.assertEqual(r.data['results'][0]['id'],str(self.work.pk))
        r=self.get('maintenance');self.assertEqual(r.data['results'][0]['planned_amount'],'125.00')
    def test_other_branch_and_contractor_cannot_use_workspace(self):
        self.assertEqual(self.client.get(f'/api/v1/assets/{self.foreign.pk}/workspace/').status_code,404)
        self.grant.role='contractor';self.grant.save();self.work.assigned_to=self.user;self.work.save()
        self.assertEqual(self.get().status_code,404)
    def test_financial_denial_applies_to_summary_lists_and_history(self):
        self.grant.finance=False;self.grant.save()
        data=self.get().data;self.assertIsNone(data['costs']['amount']);self.assertIsNone(data['counts']['maintenance'])
        self.assertEqual(self.get('costs').status_code,403);self.assertEqual(self.get('maintenance').status_code,403)
        data=self.get('history').data;self.assertEqual(data['count'],1);self.assertNotIn('after',data['results'][0]);self.assertEqual(data['results'][0]['entity'],'asset')
        self.grant.role='reader';self.grant.save();self.assertEqual(self.get('history').status_code,403)
    def test_document_versions_and_archived_work_remain_traceable(self):
        d=Document.objects.create(org=self.org,asset=self.room,title='Protokoll',file_key='x',sha256='a'*64,size=3,mime='application/pdf')
        Document.objects.create(org=self.org,asset=self.room,title='Rättat protokoll',file_key='y',sha256='b'*64,size=3,mime='application/pdf',revision_of=d)
        self.work.archived=True;self.work.save()
        self.assertEqual(self.get('documents').data['count'],2);self.assertEqual(self.get('work').data['count'],0)
        self.assertEqual(self.get().data['costs']['amount'],'0.02')
    def test_paginated_descendants_not_bootstrap_limited_and_no_cross_org_traversal(self):
        Asset.objects.bulk_create([Asset(org=self.org,parent=self.root,name=f'Byggnad {i:03}',kind='building') for i in range(60)])
        Asset.objects.create(org=self.other,parent=self.root,name='Malformed foreign relation',kind='building')
        first=self.get('objects');second=self.get('objects',page=2)
        self.assertEqual(first.data['count'],62);self.assertEqual(len(first.data['results']),50);self.assertEqual(len(second.data['results']),12)
        self.assertTrue(set(r['id'] for r in first.data['results']).isdisjoint(r['id'] for r in second.data['results']))
        self.assertEqual(self.get('objects',q='Byggnad 059').data['count'],1)
