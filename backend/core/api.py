from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
import hashlib, hmac, io, secrets, uuid, json
from datetime import date, timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler as drf_exception_handler
from rest_framework.permissions import AllowAny
from .models import *
from .access import *
from .serializers import serializer_for, OrgSerializer, CommentSerializer
from .services import *
from .auth import rate_limit, user_data


def exception_handler(exc,context):
    if isinstance(exc,ObjectDoesNotExist): exc=NotFound()
    if isinstance(exc,DjangoValidationError): exc=ValidationError(exc.message_dict if hasattr(exc,'message_dict') else exc.messages)
    if isinstance(exc,IntegrityError): exc=Conflict('Uppgiften finns redan eller krockar med en annan ändring.')
    return drf_exception_handler(exc,context)


def checked_id(value):
    try: return uuid.UUID(str(value))
    except (ValueError,TypeError): raise ValidationError('Ogiltig identifierare.')


def permitted_orgs(request,finance=False):
    ids=scope(request.user,INTERNAL,finance)
    org=request.query_params.get('org')
    if org: ids &= expand(checked_id(org))
    return ids

class OrgViewSet(viewsets.ModelViewSet):
    serializer_class=OrgSerializer
    http_method_names=['get','post','patch','head','options']
    def get_queryset(self): return OrgUnit.objects.filter(id__in=scope(self.request.user)).order_by('created_at')
    @transaction.atomic
    def create(self,request,*args,**kwargs):
        def save():
            s=self.get_serializer(data=request.data); s.is_valid(raise_exception=True)
            parent=s.validated_data.get('parent')
            if parent: require(request.user,parent.id,['admin'])
            elif not request.user.is_superuser: raise PermissionDenied()
            obj=OrgUnit(**s.validated_data); obj.full_clean(); obj.save()
            OrgRevision.objects.create(org=obj,name=obj.name,parent_id_snapshot=obj.parent_id,actor=request.user)
            audit(request.user,obj,'created'); return {'id':obj.id,'version':obj.version},201
        data,code=mutation(request,save); return Response(data,status=code)
    @transaction.atomic
    def partial_update(self,request,*args,**kwargs):
        def save():
            obj=self.get_queryset().select_for_update(of=('self',)).get(pk=kwargs['pk']); require(request.user,obj.id,['admin']); check_version(request,obj)
            # Moving a branch would also move data visibility. Explicit migration is required.
            if 'parent' in request.data and str(request.data['parent'] or '')!=str(obj.parent_id or ''): raise ValidationError('Flytt av organisationsgren kräver en granskad organisationsändring.')
            if request.data.get('kind',obj.kind)!=obj.kind: raise ValidationError('Enhetstyp kan inte ändras.')
            before=record_data(obj); s=self.get_serializer(obj,data=request.data,partial=True); s.is_valid(raise_exception=True)
            for k,v in s.validated_data.items(): setattr(obj,k,v)
            obj.version+=1; obj.full_clean(); obj.save()
            OrgRevision.objects.create(org=obj,name=obj.name,parent_id_snapshot=obj.parent_id,actor=request.user)
            audit(request.user,obj,'updated',before); return {'id':obj.id,'version':obj.version},200
        data,code=mutation(request,save); return Response(data,status=code)

class ScopedViewSet(viewsets.ModelViewSet):
    http_method_names=['get','post','patch','head','options']
    financial=False
    manage=False
    immutable=False
    model=None
    def get_queryset(self):
        qs=self.model.objects.filter(org_id__in=permitted_orgs(self.request,self.financial)).select_related('org').order_by('-created_at')
        if self.request.query_params.get('archived')!='true': qs=qs.filter(archived=False)
        if self.request.query_params.get('asset') and hasattr(self.model,'asset'): qs=qs.filter(asset_id=checked_id(self.request.query_params['asset']))
        if self.request.query_params.get('kind') and hasattr(self.model,'kind'): qs=qs.filter(kind=self.request.query_params['kind'])
        if self.request.query_params.get('q'):
            field='name' if hasattr(self.model,'name') else 'title' if hasattr(self.model,'title') else None
            if field: qs=qs.filter(**{field+'__icontains':self.request.query_params['q'][:200]})
        return qs
    def check_write(self,obj):
        require(self.request.user,obj.org_id,MANAGE if self.manage else EDIT,self.financial)
    def check_related(self,obj):
        if hasattr(obj,'asset_id') and obj.asset.archived: raise ValidationError({'asset':'Objektet är arkiverat.'})
        if hasattr(obj,'assigned_to_id') and obj.assigned_to_id:
            if obj.org_id not in scope(obj.assigned_to) or not obj.assigned_to.is_active: raise ValidationError({'assigned_to':'Utföraren saknar tillgång till enheten.'})
    def before_save(self,obj,created): pass
    @transaction.atomic
    def create(self,request,*args,**kwargs):
        def save():
            s=self.get_serializer(data=request.data); s.is_valid(raise_exception=True)
            obj=self.model(**s.validated_data); self.check_write(obj); self.check_related(obj)
            self.before_save(obj,True); obj.full_clean(); obj.save(); audit(request.user,obj,'created')
            return {'id':obj.id,'version':obj.version},201
        data,code=mutation(request,save); return Response(data,status=code)
    @transaction.atomic
    def partial_update(self,request,*args,**kwargs):
        def save():
            try: obj=self.get_queryset().select_for_update(of=('self',)).get(pk=kwargs['pk'])
            except self.model.DoesNotExist: raise NotFound()
            self.check_write(obj); check_version(request,obj)
            if self.immutable: raise ValidationError('Posten är låst. Skapa en ny revision eller korrigerande post.')
            before=record_data(obj); s=self.get_serializer(obj,data=request.data,partial=True); s.is_valid(raise_exception=True)
            for k,v in s.validated_data.items(): setattr(obj,k,v)
            self.check_related(obj); self.before_save(obj,False); obj.version+=1; obj.full_clean(); obj.save(); audit(request.user,obj,'updated',before)
            return {'id':obj.id,'version':obj.version},200
        data,code=mutation(request,save); return Response(data,status=code)

class AssetViewSet(ScopedViewSet):
    model=Asset; serializer_class=serializer_for(Asset); manage=True
    def get_queryset(self):
        if getattr(self,'swagger_fake_view',False): return self.model.objects.none()
        if scope(self.request.user,INTERNAL): return super().get_queryset()
        return Asset.objects.filter(id__in=work_scope(self.request.user).values('asset_id')).order_by('name')

class WorkViewSet(ScopedViewSet):
    model=WorkOrder; serializer_class=serializer_for(WorkOrder)
    def get_queryset(self):
        if getattr(self,'swagger_fake_view',False): return self.model.objects.none()
        qs=work_scope(self.request.user).select_related('org','asset','assigned_to').order_by('-created_at')
        if self.request.query_params.get('org'): qs=qs.filter(org_id__in=expand(checked_id(self.request.query_params['org'])))
        if self.request.query_params.get('asset') and self.request.query_params.get('include_children')=='true':
            found={checked_id(self.request.query_params['asset'])};frontier=found.copy()
            while frontier:
                frontier=set(Asset.objects.filter(parent_id__in=frontier).values_list('id',flat=True))-found;found|=frontier
            qs=qs.filter(asset_id__in=found)
        for field in ['status','kind','asset']:
            value=self.request.query_params.get(field)
            if value and not (field=='asset' and self.request.query_params.get('include_children')=='true'): qs=qs.filter(**{field:value})
        if self.request.query_params.get('q'): qs=qs.filter(Q(title__icontains=self.request.query_params['q'][:200])|Q(description__icontains=self.request.query_params['q'][:200]))
        return qs.filter(archived=False)
    def before_save(self,obj,created):
        if created: obj.number=number()
        else:
            if obj.status in ['verified','cancelled']: raise ValidationError('Avslutat ärende kan inte redigeras. Återöppna först.')
    def check_write(self,obj):
        if obj._state.adding: return super().check_write(obj)
        if not can_work(self.request.user,obj): raise PermissionDenied()
        if obj.org_id not in scope(self.request.user,EDIT):
            if set(self.request.data)-{'version','checklist_results'}: raise PermissionDenied('Du kan bara registrera kontrollsvar på det tilldelade uppdraget.')
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def transition(self,request,pk=None):
        def save():
            obj=self.get_queryset().select_for_update(of=('self',)).get(pk=pk); check_version(request,obj)
            if not can_work(request.user,obj): raise PermissionDenied()
            target=request.data.get('status')
            transitions={'new':['planned','in_progress','cancelled'],'planned':['in_progress','cancelled'],'in_progress':['completed','cancelled'],'completed':['verified','in_progress'],'verified':['in_progress'],'cancelled':['planned']}
            if target not in transitions[obj.status]: raise ValidationError('Statusövergången är inte tillåten.')
            if target in ['verified','cancelled'] or obj.status in ['verified','cancelled']: require(request.user,obj.org_id,MANAGE)
            if target=='completed' and any(str(i) not in obj.checklist_results for i in range(len(obj.checklist))): raise ValidationError('Besvara samtliga kontrollpunkter innan du kvitterar.')
            before=record_data(obj); obj.status=target; obj.version+=1
            if target=='completed': obj.completed_at=timezone.now()
            if target=='verified': obj.verified_at=timezone.now()
            if target=='in_progress': obj.verified_at=None
            obj.save(); audit(request.user,obj,'status_changed',before)
            if obj.reporter_email: enqueue('status_email',{'work':str(obj.id)},f'status:{obj.id}:{obj.version}')
            return {'id':obj.id,'version':obj.version},200
        data,code=mutation(request,save); return Response(data,status=code)
    @action(detail=True,methods=['get','post'])
    def comments(self,request,pk=None):
        obj=self.get_object()
        if request.method=='GET':
            qs=obj.comments.order_by('created_at')
            if obj.org_id not in scope(request.user,INTERNAL): qs=qs.exclude(visibility='internal')
            return Response(CommentSerializer(qs,many=True).data)
        with transaction.atomic():
            def save():
                if not can_work(request.user,obj): raise PermissionDenied()
                s=CommentSerializer(data=request.data); s.is_valid(raise_exception=True)
                if len(s.validated_data['text'])>20000: raise ValidationError('Kommentaren är för lång.')
                if obj.org_id not in scope(request.user,EDIT) and s.validated_data.get('visibility','internal')!='contractor': raise PermissionDenied('Entreprenörer kan skriva uppdragskommentarer.')
                c=s.save(work=obj,author=request.user)
                AuditEvent.objects.create(org=obj.org,actor=request.user,entity='workcomment',entity_id=str(c.id),action='created',after={'work':str(obj.id),'visibility':c.visibility})
                if c.visibility=='public' and obj.reporter_email: enqueue('status_email',{'work':str(obj.id)},f'comment:{c.id}')
                return {'id':c.id},201
            data,code=mutation(request,save); return Response(data,status=code)
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def deviation(self,request,pk=None):
        def save():
            parent=self.get_queryset().select_for_update(of=('self',)).get(pk=pk)
            if not can_work(request.user,parent): raise PermissionDenied()
            index=str(request.data.get('index',''))
            if parent.checklist_results.get(index)!='deviation': raise ValidationError('Välj en kontrollpunkt med avvikelse.')
            title=f'Avvikelse: {parent.checklist[int(index)]}'
            child=WorkOrder(org=parent.org,asset=parent.asset,number=number(),title=title[:200],description=f'Från arbetsorder #{parent.number}. '+str(request.data.get('description',''))[:5000],category=parent.category,assigned_to=parent.assigned_to)
            child.full_clean(); child.save(); audit(request.user,child,'deviation_created')
            return {'id':child.id,'version':child.version},201
        data,code=mutation(request,save); return Response(data,status=code)

class ScheduleViewSet(ScopedViewSet):
    model=Schedule; serializer_class=serializer_for(Schedule); manage=True
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def generate(self,request,pk=None):
        def save():
            obj=self.get_object(); self.check_write(obj)
            count=generate_schedule(obj.id); return {'id':obj.id,'generated':count},200
        data,code=mutation(request,save); return Response(data,status=code)

class MaintenanceViewSet(ScopedViewSet):
    model=Maintenance; serializer_class=serializer_for(Maintenance); financial=True; manage=True
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def order(self,request,pk=None):
        def save():
            obj=self.get_queryset().select_for_update(of=('self',)).get(pk=pk); self.check_write(obj); check_version(request,obj)
            if obj.work_id: return {'id':obj.work_id},200
            work=WorkOrder.objects.create(org=obj.org,asset=obj.asset,number=number(),title=obj.title,description=obj.note,due_date=date(obj.year,12,31),category='Planerat underhåll')
            obj.work=work; obj.version+=1; obj.save(); audit(request.user,work,'maintenance_order'); audit(request.user,obj,'order_linked')
            return {'id':work.id},201
        data,code=mutation(request,save); return Response(data,status=code)

class CostViewSet(ScopedViewSet):
    model=CostEntry; serializer_class=serializer_for(CostEntry); financial=True; immutable=True
    def get_queryset(self):
        qs=super().get_queryset()
        return qs.filter(work_id=self.request.query_params['work']) if self.request.query_params.get('work') else qs

class RegistryViewSet(ScopedViewSet):
    model=RegistryEntry; serializer_class=serializer_for(RegistryEntry)
class MeterViewSet(ScopedViewSet):
    model=Meter; serializer_class=serializer_for(Meter); manage=True
class ReadingViewSet(ScopedViewSet):
    model=Reading; serializer_class=serializer_for(Reading); immutable=True
    def get_queryset(self):
        qs=super().get_queryset()
        return qs.filter(meter_id=self.request.query_params['meter']) if self.request.query_params.get('meter') else qs
    def before_save(self,obj,created):
        Meter.objects.select_for_update(of=('self',)).get(pk=obj.meter_id); validate_reading(obj)
class KeyViewSet(ScopedViewSet):
    model=Key; serializer_class=serializer_for(Key); manage=True
class KeyLoanViewSet(ScopedViewSet):
    model=KeyLoan; serializer_class=serializer_for(KeyLoan); manage=True; immutable=True
    def before_save(self,obj,created):
        key=Key.objects.select_for_update(of=('self',)).get(pk=obj.key_id)
        if key.org_id!=obj.org_id or key.archived: raise ValidationError('Fel nyckel eller organisationsenhet.')
        if key.condition!='ok': raise ValidationError('Nyckeln är skadad eller borttappad.')
        if KeyLoan.objects.filter(key=key,returned_at__isnull=True).exists(): raise Conflict('Nyckeln är redan utlånad.')
        if obj.due_date<timezone.localdate(): raise ValidationError('Återlämningsdatum har passerat.')
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def return_key(self,request,pk=None):
        def save():
            obj=self.get_queryset().select_for_update(of=('self',)).get(pk=pk); self.check_write(obj); check_version(request,obj)
            if obj.returned_at: raise Conflict('Nyckeln är redan återlämnad.')
            before=record_data(obj); obj.returned_at=timezone.now(); obj.version+=1; obj.save(); audit(request.user,obj,'returned',before)
            return {'id':obj.id,'version':obj.version},200
        data,code=mutation(request,save); return Response(data,status=code)

class DocumentViewSet(ScopedViewSet):
    model=Document; serializer_class=serializer_for(Document); immutable=True
    def get_queryset(self):
        if getattr(self,'swagger_fake_view',False): return self.model.objects.none()
        if scope(self.request.user,INTERNAL): return super().get_queryset()
        return Document.objects.filter(work__in=work_scope(self.request.user),shared_contractor=True).select_related('org','asset').order_by('-created_at')
    @transaction.atomic
    def create(self,request,*args,**kwargs):
        from .storage import inspect_upload,put_file
        data,mime,sha=inspect_upload(request.FILES.get('file'))
        def save():
            asset=Asset.objects.filter(pk=checked_id(request.data.get('asset')),org_id__in=scope(request.user,EDIT)).first()
            if not asset: raise PermissionDenied()
            work=None
            if request.data.get('work'):
                work=work_scope(request.user).filter(pk=checked_id(request.data['work']),asset=asset).first()
                if not work: raise ValidationError('Fel arbetsorder.')
            prev=None
            if request.data.get('revision_of'):
                prev=self.get_queryset().filter(pk=checked_id(request.data['revision_of']),asset=asset).first()
                if not prev: raise ValidationError('Fel dokumentversion.')
            obj=Document(org=asset.org,asset=asset,work=work,title=request.data.get('title','')[:180] or request.FILES['file'].name[:180],file_key='pending',sha256=sha,size=len(data),mime=mime,revision_of=prev,shared_contractor=request.data.get('shared_contractor')=='true',uploaded_by=request.user)
            obj.full_clean(); obj.file_key=put_file(data); obj.save(); audit(request.user,obj,'uploaded')
            return {'id':obj.id,'version':obj.version},201
        result,code=mutation(request,save,sha); return Response(result,status=code)
    @action(detail=True,methods=['get'])
    def download(self,request,pk=None):
        from .storage import read_file
        obj=self.get_object(); data=read_file(obj)
        AuditEvent.objects.create(org=obj.org,actor=request.user,entity='document',entity_id=str(obj.id),action='downloaded')
        suffix={'application/pdf':'.pdf','image/png':'.png','image/jpeg':'.jpg'}[obj.mime]
        return FileResponse(io.BytesIO(data),as_attachment=True,filename=obj.title+suffix,content_type=obj.mime)

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class AuditView(APIView):
    def get(self,request):
        qs=AuditEvent.objects.filter(org_id__in=scope(request.user,MANAGE)).order_by('-id')
        if request.query_params.get('entity_id'): qs=qs.filter(entity_id=request.query_params['entity_id'])
        # Metadata only: audit payloads may include financial or personal fields.
        return Response(list(qs.values('id','entity','entity_id','action','created_at','actor__username')[:100]))

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class ReceiptView(APIView):
    def get(self,request,key):
        receipt=MutationReceipt.objects.filter(user=request.user,key=key).first()
        return Response({'saved':bool(receipt),'result':receipt.response if receipt else None})

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class BootstrapView(APIView):
    def get(self,request):
        ids=permitted_orgs(request); works=work_scope(request.user)
        if request.query_params.get('org'): works=works.filter(org_id__in=expand(checked_id(request.query_params['org'])))
        today=timezone.localdate()
        open_work=works.exclude(status__in=['verified','cancelled'])
        grants=list(Membership.objects.filter(user=request.user,active=True).values('org_id','role','finance','descendants'))
        assets=AssetViewSet(); assets.request=request
        return Response({'user':user_data(request.user),'organizations':OrgSerializer(OrgUnit.objects.filter(id__in=scope(request.user)).order_by('created_at'),many=True).data,'assets':serializer_for(Asset)(assets.get_queryset()[:1000],many=True).data,'grants':grants,'finance_orgs':list(scope(request.user,INTERNAL,True)),'edit_orgs':list(scope(request.user,EDIT)),'manage_orgs':list(scope(request.user,MANAGE)),'admin_orgs':list(scope(request.user,['admin'])),'stats':{'assets':Asset.objects.filter(org_id__in=ids,archived=False).count(),'open':open_work.count(),'overdue':open_work.filter(due_date__lt=today).count(),'upcoming':works.filter(kind__in=['round','inspection'],due_date__gte=today,due_date__lte=today+timedelta(days=30)).exclude(status__in=['verified','cancelled']).count()},'work':serializer_for(WorkOrder)(open_work.select_related('org','asset','assigned_to').order_by('due_date')[:8],many=True).data,'demo':settings.DEMO_MODE})

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class PublicAssets(APIView):
    authentication_classes=[]; permission_classes=[AllowAny]
    def get(self,request):
        rate_limit(request,'public-assets',120,60)
        return Response(list(Asset.objects.filter(public=True,archived=False).values('id','name','address')[:500]))

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class PublicIssue(APIView):
    authentication_classes=[]; permission_classes=[AllowAny]
    def post(self,request):
        rate_limit(request,'public-issue',10,3600)
        from django.core.validators import validate_email
        try: key=uuid.UUID(request.headers.get('Idempotency-Key',''))
        except ValueError: raise ValidationError('Sparnyckel saknas.')
        title=str(request.data.get('title','')).strip(); description=str(request.data.get('description','')).strip(); email=str(request.data.get('email','')).strip()
        if not title or len(title)>200 or len(description)>10000: raise ValidationError('Ange en rubrik på högst 200 tecken och beskrivning på högst 10 000 tecken.')
        if request.data.get('website'): raise ValidationError('Anmälan kunde inte tas emot.')
        if email: validate_email(email)
        asset=Asset.objects.filter(pk=checked_id(request.data.get('asset')),public=True,archived=False).first()
        if not asset: raise NotFound()
        digest=hashlib.sha256(json.dumps([str(asset.id),title,description,email],ensure_ascii=False).encode()).hexdigest()
        # Derived only from a secret and a random client request key; never sequential IDs.
        token=hmac.new(settings.SECRET_KEY.encode(),('public:'+str(key)).encode(),hashlib.sha256).hexdigest()
        with transaction.atomic():
            Asset.objects.select_for_update(of=('self',)).get(pk=asset.id)
            previous=PublicReceipt.objects.filter(key=key).first()
            if previous:
                if previous.fingerprint!=digest: raise Conflict()
                work=previous.work
            else:
                work=WorkOrder(org=asset.org,asset=asset,number=number(),title=title,description=description,reporter_email=email,source='public',public_token_hash=hashlib.sha256(token.encode()).hexdigest())
                work.full_clean(); work.save(); PublicReceipt.objects.create(key=key,fingerprint=digest,work=work); audit(None,work,'public_issue')
                if email: enqueue('public_receipt',{'work':str(work.id),'receipt_key':str(key)},f'receipt:{work.id}')
        return Response({'number':work.number,'token':token},status=201)

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class PublicTrack(APIView):
    authentication_classes=[]; permission_classes=[AllowAny]
    def post(self,request):
        rate_limit(request,'public-track',60,60)
        token=str(request.data.get('token',''))
        if len(token)!=64: raise NotFound()
        work=WorkOrder.objects.filter(public_token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
        if not work: raise NotFound()
        return Response({'number':work.number,'title':work.title,'status':work.status,'created_at':work.created_at,'comments':list(work.comments.filter(visibility='public').values('text','created_at'))})
