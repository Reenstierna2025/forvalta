"""Versioned inspection protocols and explicit finding follow-up."""
import copy,uuid
from datetime import date
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError,PermissionDenied
from .models import Inspection,InspectionFinding,Asset,Document,WorkOrder
from .api import ScopedViewSet,checked_id
from .access import scope,INTERNAL,EDIT,MANAGE,require
from .services import mutation,check_version,audit,record_data,number,Conflict,jsonable
from .serializers import serializer_for
TEMPLATES={
 'sba':{'name':'SBA – grundkontroll','items':['Utrymningsvägar är fria','Släckutrustning är tillgänglig','Branddörrar kan stängas','Skyltning och nödbelysning kontrollerad']},
 'safety':{'name':'Skyddsrond – grundkontroll','items':['Gångytor och trappor är säkra','Belysning fungerar','Arbetsutrustning kontrollerad','Identifierade arbetsmiljörisker dokumenterade']},
 'building':{'name':'Byggnad – okulär grundkontroll','items':['Tak och avvattning kontrollerade','Fasad och fönster kontrollerade','Synliga fukttecken kontrollerade','Ventilation och inomhusmiljö kontrollerade']}}
RESULTS={'pass':'Utan anmärkning','fail':'Anmärkning','na':'Ej tillämpligt'}

def validate_answers(obj,answers,complete=False):
    if not isinstance(answers,dict) or set(answers)-{x['key'] for x in obj.items}:raise ValidationError('Okända kontrollpunkter.')
    clean={}
    for item in obj.items:
        a=answers.get(item['key'],{})
        if not isinstance(a,dict):raise ValidationError('Ogiltigt kontrollsvar.')
        result=a.get('result','');note=str(a.get('note','')).strip();docs=a.get('documents',[])
        if result not in ['',*RESULTS] or len(note)>4000:raise ValidationError('Ogiltigt svar eller för lång kommentar.')
        if complete and (not result or (result in ['fail','na'] and not note)):raise ValidationError('Besvara alla punkter och motivera anmärkningar/ej tillämpligt.')
        if not isinstance(docs,list) or len(docs)>10:raise ValidationError('Högst tio bilagor per punkt.')
        ids={checked_id(d) for d in docs}
        if Document.objects.filter(pk__in=ids,org=obj.org,asset=obj.asset).count()!=len(ids):raise ValidationError('Bilagan måste höra till samma objekt och enhet.')
        clean[item['key']]={'result':result,'note':note,'documents':sorted(str(d) for d in ids)}
    return clean

class InspectionViewSet(ScopedViewSet):
    model=Inspection;serializer_class=serializer_for(Inspection);http_method_names=['get','post','patch','head','options']
    def get_queryset(self):
        return super().get_queryset().select_related('asset')
    @action(detail=False,methods=['get'])
    def templates(self,request):return Response(TEMPLATES)
    @action(detail=False,methods=['get'])
    def overview(self,request):
        from .api import permitted_orgs
        qs=self.get_queryset();today=timezone.localdate()
        findings=InspectionFinding.objects.filter(org_id__in=permitted_orgs(request),state='open')
        return Response({'planned':qs.filter(state='draft',scheduled_date__gte=today).count(),'overdue':qs.filter(state='draft',scheduled_date__lt=today).count(),'open_findings':findings.count(),'findings':list(findings.order_by('created_at').values('id','title','inspection_id')[:20])})
    @transaction.atomic
    def create(self,request,*args,**kwargs):
        def save():
            asset=Asset.objects.filter(pk=checked_id(request.data.get('asset')),org_id__in=scope(request.user,EDIT),archived=False).first()
            if not asset:raise PermissionDenied()
            template=TEMPLATES.get(request.data.get('template'))
            if not template:raise ValidationError('Välj kontrollmall.')
            try:scheduled=date.fromisoformat(str(request.data.get('scheduled_date')))
            except ValueError:raise ValidationError('Ange kontrollens planerade datum.')
            labels=request.data.get('items',template['items'])
            if not isinstance(labels,list) or not 1<=len(labels)<=100 or any(not isinstance(x,str) or not x.strip() or len(x)>300 for x in labels):raise ValidationError('Ange 1–100 kontrollpunkter på högst 300 tecken.')
            obj=Inspection(org=asset.org,asset=asset,title=str(request.data.get('title','')).strip(),scheduled_date=scheduled,template_name=template['name'],items=[{'key':str(uuid.uuid4()),'label':x.strip()} for x in labels])
            obj.full_clean(exclude=['answers','snapshot']);obj.save();audit(request.user,obj,'inspection_planned');return {'id':obj.pk,'version':obj.version},201
        result,status=mutation(request,save);return Response(result,status=status)
    @transaction.atomic
    def partial_update(self,request,*args,**kwargs):
        def save():
            obj=self.get_queryset().select_for_update(of=('self',)).get(pk=kwargs['pk']);require(request.user,obj.org_id,EDIT);check_version(request,obj)
            if obj.state!='draft':raise Conflict('Fastställt protokoll är låst. Skapa en rättelse.')
            if set(request.data)-{'version','answers'}:raise ValidationError('Endast kontrollsvar får ändras här.')
            before=record_data(obj);obj.answers=validate_answers(obj,request.data.get('answers'));obj.version+=1;obj.save();audit(request.user,obj,'inspection_saved',before);return {'id':obj.pk,'version':obj.version},200
        result,status=mutation(request,save);return Response(result,status=status)
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def publish(self,request,pk=None):
        def save():
            candidate=self.get_queryset().get(pk=pk)
            Inspection.objects.select_for_update().filter(series=candidate.series).order_by('created_at','id').first()
            obj=self.get_queryset().select_for_update(of=('self',)).get(pk=pk);require(request.user,obj.org_id,MANAGE);check_version(request,obj)
            if obj.state!='draft':raise Conflict('Protokollet är redan fastställt.')
            obj.answers=validate_answers(obj,obj.answers,True)
            docs={d for a in obj.answers.values() for d in a['documents']}
            obj.snapshot=jsonable({'asset':obj.asset.name,'org':obj.org.name,'author':request.user.get_full_name() or request.user.username,'items':obj.items,'answers':obj.answers,'documents':list(Document.objects.filter(pk__in=docs).values('id','title','sha256','size','mime'))})
            for item in obj.items:
                a=obj.answers[item['key']]
                if a['result']=='fail':
                    finding,created=InspectionFinding.objects.get_or_create(series=obj.series,item_key=item['key'],defaults={'inspection':obj,'org':obj.org,'title':item['label'],'note':a['note']})
                    if created:audit(request.user,finding,'finding_created')
                    elif finding.state=='verified':
                        before=record_data(finding);finding.state='open';finding.inspection=obj;finding.note=a['note'];finding.work=None;finding.verified_by=None;finding.verified_at=None;finding.verification=None;finding.version+=1;finding.save();audit(request.user,finding,'finding_reopened',before)
            obj.state='published';obj.published_at=timezone.now();obj.version+=1;obj.save();audit(request.user,obj,'inspection_published');return {'id':obj.pk,'version':obj.version},200
        result,status=mutation(request,save);return Response(result,status=status)
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def followup(self,request,pk=None):
        def save():
            source=self.get_queryset().select_for_update(of=('self',)).get(pk=pk);require(request.user,source.org_id,MANAGE);check_version(request,source)
            if source.state!='published':raise ValidationError('Utgå från ett fastställt protokoll.')
            mode=request.data.get('mode');reason=str(request.data.get('reason','')).strip()
            if mode not in ['correction','followup'] or not 5<=len(reason)<=500:raise ValidationError('Välj rättelse/ombesiktning och ange skäl på 5–500 tecken.')
            try:scheduled=date.fromisoformat(str(request.data.get('scheduled_date')))
            except ValueError:raise ValidationError('Ange datum.')
            obj=Inspection.objects.create(org=source.org,asset=source.asset,series=source.series,title=source.title,scheduled_date=scheduled,template_name=source.template_name,items=copy.deepcopy(source.items),answers=copy.deepcopy(source.answers) if mode=='correction' else {},supersedes=source if mode=='correction' else None,follow_up_of=source if mode=='followup' else source.follow_up_of,reason=reason)
            audit(request.user,obj,'inspection_'+mode);return {'id':obj.pk,'version':obj.version},201
        result,status=mutation(request,save);return Response(result,status=status)
    @action(detail=True,methods=['get'])
    def protocol(self,request,pk=None):
        from .reports import export_report
        obj=self.get_object()
        if obj.state!='published':raise ValidationError('Fastställ protokollet före export.')
        s=obj.snapshot;rows=[]
        for item in s['items']:
            a=s['answers'][item['key']];rows.append({'Kontrollpunkt':item['label'],'Resultat':RESULTS[a['result']],'Kommentar':a['note'] or None,'Bilagor':', '.join(d['title']+' ['+str(d['id'])+']' for d in s['documents'] if str(d['id']) in a['documents']) or None})
        return export_report(jsonable({'title':obj.title,'generated_at':obj.published_at,'calculation_version':'inspection-1','definitions':'Fastställt kontrollprotokoll. Grundmallen är ett arbetsstöd och ska anpassas till objektets krav. Bilagor bevaras separat med kontrollsummor.','filters':{'protocol':str(obj.pk),'version':obj.version,'asset':s['asset'],'org':s['org'],'author':s['author'],'date':obj.scheduled_date,'supersedes':str(obj.supersedes_id) if obj.supersedes_id else None,'follow_up_of':str(obj.follow_up_of_id) if obj.follow_up_of_id else None,'reason':obj.reason},'rows':rows,'totals':{}}),request.query_params.get('format_file','pdf'))

class FindingViewSet(ScopedViewSet):
    model=InspectionFinding;serializer_class=serializer_for(InspectionFinding);http_method_names=['get','post','head','options']
    def create(self,*args,**kwargs):raise ValidationError('Anmärkningar skapas genom fastställande av protokoll.')
    def get_queryset(self):
        qs=super().get_queryset().select_related('inspection','work')
        if self.request.query_params.get('series'):qs=qs.filter(series=checked_id(self.request.query_params['series']))
        return qs
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def order(self,request,pk=None):
        def save():
            f=self.get_queryset().select_for_update(of=('self',)).get(pk=pk);require(request.user,f.org_id,EDIT);check_version(request,f)
            if f.state=='verified':raise Conflict('Anmärkningen är verifierad.')
            if f.work_id:return {'id':f.work_id},200
            try:due=date.fromisoformat(str(request.data.get('due_date')))
            except ValueError:raise ValidationError('Ange sista åtgärdsdatum.')
            from django.contrib.auth import get_user_model
            try:user=get_user_model().objects.filter(pk=int(request.data.get('assigned_to')),is_active=True).first()
            except (ValueError,TypeError):user=None
            if not user or f.org_id not in scope(user):raise ValidationError('Välj en ansvarig med åtkomst till enheten.')
            w=WorkOrder(org=f.org,asset=f.inspection.asset,title=f.title,description=f.note,number=number(),priority=request.data.get('priority','normal'),due_date=due,assigned_to=user,kind='issue',category='Besiktning',source='inspection');w.full_clean();w.save()
            before=record_data(f);f.work=w;f.version+=1;f.save();audit(request.user,w,'inspection_order');audit(request.user,f,'finding_order_linked',before);return {'id':w.pk},201
        result,status=mutation(request,save);return Response(result,status=status)
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def verify(self,request,pk=None):
        def save():
            candidate=self.get_queryset().get(pk=pk)
            Inspection.objects.select_for_update().filter(series=candidate.series).order_by('created_at','id').first()
            f=self.get_queryset().select_for_update(of=('self',)).get(pk=pk);require(request.user,f.org_id,MANAGE);check_version(request,f)
            check=Inspection.objects.filter(pk=checked_id(request.data.get('inspection')),org=f.org,series=f.series,state='published',follow_up_of__isnull=False).first()
            if not check or check.published_at<=f.inspection.published_at or check.answers.get(f.item_key,{}).get('result')!='pass':raise ValidationError('En senare fastställd ombesiktning måste godkänna kontrollpunkten.')
            latest=Inspection.objects.filter(series=f.series,state='published').order_by('-published_at').first()
            if latest.pk!=check.pk:raise Conflict('Använd den senaste fastställda ombesiktningen.')
            if f.work_id and WorkOrder.objects.select_for_update().get(pk=f.work_id).status not in ['completed','verified']:raise ValidationError('Arbetsordern måste vara kvitterad eller verifierad.')
            if f.state=='verified':raise Conflict('Redan verifierad.')
            before=record_data(f);f.state='verified';f.verification=check;f.verified_by=request.user;f.verified_at=timezone.now();f.version+=1;f.save();audit(request.user,f,'finding_verified',before);return {'id':f.pk,'version':f.version},200
        result,status=mutation(request,save);return Response(result,status=status)
