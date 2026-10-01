from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from django.utils import timezone
from core.models import *
from core.services import number,audit,generate_schedule

class Command(BaseCommand):
    help='Create isolated synthetic demonstration data. Never permitted in production.'
    @transaction.atomic
    def handle(self,*args,**options):
        if not settings.DEBUG or not settings.DEMO_MODE: raise CommandError('Requires DEBUG=1 and DEMO_MODE=1')
        if OrgUnit.objects.exists(): raise CommandError('Only an empty database may be seeded')
        User=get_user_model(); demo=User.objects.create(username='demo',first_name='Alex',last_name='Lind',email='demo@example.invalid'); demo.set_unusable_password(); demo.save()
        worker=User.objects.create(username='elin',first_name='Elin',last_name='Berg',email='elin@example.invalid'); worker.set_unusable_password(); worker.save()
        external=User.objects.create(username='entreprenor',first_name='Norrsken',last_name='Service',email='service@example.invalid'); external.set_unusable_password(); external.save()
        parent=None; orgs=[]
        for kind,name in [('church','Svenska kyrkan'),('diocese','Exempelstiftet'),('pastorate','Åsby pastorat'),('parish','Åsby församling')]:
            parent=OrgUnit.objects.create(name=name,kind=kind,parent=parent); orgs.append(parent)
            OrgRevision.objects.create(org=parent,name=name,parent_id_snapshot=parent.parent_id,actor=demo)
        org=parent
        Membership.objects.create(user=demo,org=orgs[0],role='admin',descendants=True,finance=True)
        Membership.objects.create(user=worker,org=org,role='worker')
        Membership.objects.create(user=external,org=org,role='contractor')
        props=[]; buildings=[]
        for name,address,area in [('Åsby kyrka','Kyrkvägen 1',640),('Lunden församlingshem','Lundgatan 12',1120),('Björkbackens kapell','Björkallén 4',280),('Åsby kyrkogård','Kyrkvägen 3',12500)]:
            prop=Asset.objects.create(org=org,name=name,kind='property',address=address,designation='Exempel 1:'+str(len(props)+1),owner='Åsby församling',manager='Åsby pastorat',public=True,description='Fiktivt objekt för demonstration.'); props.append(prop)
            building=Asset.objects.create(org=org,parent=prop,name=name+' · '+('Markområde' if 'kyrkogård' in name else 'Huvudbyggnad'),kind='land' if 'kyrkogård' in name else 'building',area=area,address=address); buildings.append(building)
            audit(demo,prop,'created')
        today=timezone.localdate()
        works=[('Kontrollera läckage vid sakristian',0,'urgent','in_progress',-2,'issue',worker),('Höstkontroll av tak och hängrännor',0,'normal','planned',2,'round',worker),('Justera ventilation i samlingssalen',1,'high','in_progress',0,'issue',external),('Årlig brandskyddskontroll',2,'high','planned',7,'inspection',worker),('Byt ljuskälla vid entrén',1,'normal','new',1,'issue',None),('Beskärning längs norra gången',3,'normal','planned',12,'issue',external),('Kontroll av branddörrar',1,'normal','completed',-1,'round',worker),('Åtgärda löst trappräcke',2,'high','verified',-7,'issue',worker)]
        created=[]
        for title,b,priority,state,offset,kind,assignee in works:
            w=WorkOrder.objects.create(org=org,asset=buildings[b],number=number(),title=title,description='Exempeluppgift. Kontrollera på plats och dokumentera utförd åtgärd.',priority=priority,status=state,due_date=today+timedelta(days=offset),kind=kind,assigned_to=assignee,checklist=['Kontrollera skick','Dokumentera avvikelser'] if kind!='issue' else [])
            if state in ['completed','verified']: w.completed_at=timezone.now(); w.checklist_results={'0':'ok','1':'ok'} if w.checklist else {}; w.save()
            if state=='verified': w.verified_at=timezone.now(); w.save()
            audit(demo,w,'created'); created.append(w)
        for title,idx,offset,qty,price,interval in [('Renovering av takavvattning',0,0,45,1650,20),('Byte av ventilationsaggregat',1,1,1,285000,20),('Målning av fasad',2,2,240,780,12),('Tillgänglig entré',1,0,1,148000,0),('Omläggning av gångstråk',3,3,400,420,15),('Konservering av inventarier',0,4,1,96000,10)]:
            m=Maintenance.objects.create(org=org,asset=buildings[idx],title=title,year=today.year+offset,price_year=today.year,quantity=qty,unit_price=price,interval_years=interval,cost_factor=Decimal('1.25'),index_percent=Decimal('2.00'),unit='st' if qty==1 else 'm²',account='Underhåll',funding_possible=Decimal('20000') if idx==0 else 0)
            audit(demo,m,'created')
        CostEntry.objects.create(org=org,work=created[0],kind='time',description='Felsökning tak',date=today,quantity=8,unit_price=650)
        CostEntry.objects.create(org=org,work=created[2],kind='material',description='Ventilationsfilter',date=today,quantity=4,unit_price=1250)
        Schedule.objects.create(org=org,asset=buildings[0],title='Månadsrond · kyrkobyggnad',kind='round',anchor_date=today,next_date=today+timedelta(days=30),checklist=['Tak och avvattning','Dörrar och lås','Belysning och el','Brandskydd'],assigned_to=worker)
        Schedule.objects.create(org=org,asset=buildings[1],title='Brandskyddsrond',kind='inspection',category='SBA',anchor_date=today,next_date=today+timedelta(days=14),checklist=['Utrymningsvägar','Släckutrustning','Branddörrar'],assigned_to=worker)
        for kind,title,b in [('care_plan','Vårdplan för kyrkobyggnaden',0),('tree','Lindallén · trädinventering',3),('inventory','Ljuskrona i långhuset',0),('contract','Serviceavtal ventilation',1),('warranty','Garanti · takarbete',2),('sba','Systematiskt brandskyddsarbete',1)]: RegistryEntry.objects.create(org=org,asset=buildings[b],kind=kind,title=title,description='Syntetiskt exempelunderlag.',responsible='Elin Berg',due_date=today+timedelta(days=45))
        meter=Meter.objects.create(org=org,asset=buildings[1],name='El · församlingshem',medium='electricity',unit='kWh',serial='DEMO-001')
        for days,value in [(90,102400),(60,106100),(30,109300),(0,113700)]: Reading.objects.create(org=org,meter=meter,date=today-timedelta(days=days),value=value)
        key=Key.objects.create(org=org,asset=buildings[0],name='Huvudentré · nyckel 01',system='Exempelsystem',serial='01')
        KeyLoan.objects.create(org=org,key=key,borrower='Exempelentreprenör',due_date=today+timedelta(days=7))
        self.stdout.write(self.style.SUCCESS('Synthetic demonstration created. Local demo sign-in is enabled.'))
