"""Read-only property workspace, scoped to one explicit organization and asset tree."""
from decimal import Decimal
from django.db import connection,transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound,PermissionDenied,ValidationError
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from .models import Asset,WorkOrder,Schedule,Maintenance,Document,CostEntry,AuditEvent,RegistryEntry,WorkComment
from .access import scope,INTERNAL,EDIT,MANAGE
from .serializers import serializer_for

class WorkspacePages(PageNumberPagination):page_size=50


def asset_tree(root):
    found={root.pk};frontier=found.copy()
    while frontier:
        frontier=set(Asset.objects.filter(parent_id__in=frontier,org_id=root.org_id).values_list('pk',flat=True))-found
        found|=frontier
    return found

@extend_schema(responses=OpenApiTypes.OBJECT)
class PropertyWorkspace(APIView):
    def get(self,request,pk):
        outer=connection.in_atomic_block
        with transaction.atomic():
            if connection.vendor=='postgresql' and not outer:
                with connection.cursor() as cursor:cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            return self.read(request,pk)

    def read(self,request,pk):
        root=Asset.objects.filter(pk=pk,org_id__in=scope(request.user,INTERNAL),archived=False).select_related('org').first()
        if not root:raise NotFound('Den samlade fastighetsvyn kräver intern åtkomst till objektet.')
        ids=asset_tree(root);finance=root.org_id in scope(request.user,INTERNAL,True);manage=root.org_id in scope(request.user,MANAGE)
        works=WorkOrder.objects.filter(org_id=root.org_id,asset_id__in=ids)
        schedules=Schedule.objects.filter(org_id=root.org_id,asset_id__in=ids,archived=False)
        documents=Document.objects.filter(org_id=root.org_id,asset_id__in=ids)
        maintenance=Maintenance.objects.filter(org_id=root.org_id,asset_id__in=ids,archived=False)
        costs=CostEntry.objects.filter(org_id=root.org_id,work__in=works)
        section=request.query_params.get('section','summary');today=timezone.localdate()
        if section=='summary':
            active=works.filter(archived=False);open_work=active.exclude(status__in=['verified','cancelled'])
            year_costs=costs.filter(date__year=today.year)
            # Round each line using the same Decimal rule as the costs API, then sum.
            amount=sum((c.total for c in year_costs.only('quantity','unit_price').iterator()),Decimal('0.00')) if finance else None
            ancestors=[];current=root;seen={root.pk}
            while current.parent_id:
                parent=Asset.objects.filter(pk=current.parent_id,org_id=root.org_id).first()
                if not parent or parent.pk in seen:break
                ancestors.append({'id':str(parent.pk),'name':parent.name,'archived':parent.archived});seen.add(parent.pk);current=parent
            return Response({'asset':serializer_for(Asset)(root).data,'ancestors':list(reversed(ancestors)),'scope':'Objektet och samtliga underobjekt inom samma organisationsenhet. Dokument och historik inkluderar arkiverade poster.','generated_at':timezone.now(),'permissions':{'edit':root.org_id in scope(request.user,EDIT),'manage':manage,'history':manage,'finance':finance},'counts':{'objects':Asset.objects.filter(pk__in=ids,archived=False).count()-1,'work':active.count(),'open':open_work.count(),'overdue':open_work.filter(due_date__lt=today).count(),'awaiting_verification':active.filter(status='completed').count(),'schedules':schedules.count(),'documents':documents.count(),'maintenance':maintenance.count() if finance else None},'costs':{'year':today.year,'amount':str(amount) if amount is not None else None,'entries':year_costs.count() if finance else None,'definition':'Summan av registrerade kostnadsrader daterade under kalenderåret, avrundade per rad till ören. Inkluderar avslutade och arkiverade arbetsorder; är inte budget eller fullständig bokföring.'}})
        if section=='objects':
            qs=Asset.objects.filter(pk__in=ids,archived=False).exclude(pk=root.pk).select_related('org').order_by('name','id');model=Asset
        elif section=='work':
            qs=works.filter(archived=False).select_related('org','asset','assigned_to').order_by('due_date','number');model=WorkOrder
            status=request.query_params.get('status','')
            if status=='overdue':qs=qs.filter(due_date__lt=today).exclude(status__in=['verified','cancelled'])
            elif status=='open':qs=qs.exclude(status__in=['verified','cancelled'])
            elif status:
                if status not in ['new','planned','in_progress','completed','verified','cancelled']:raise ValidationError('Ogiltig status.')
                qs=qs.filter(status=status)
        elif section=='schedules':qs=schedules.select_related('org','asset').order_by('next_date','id');model=Schedule
        elif section=='documents':qs=documents.select_related('org','asset').order_by('-created_at','id');model=Document
        elif section=='maintenance':
            if not finance:raise PermissionDenied('Ekonomibehörighet krävs.')
            qs=maintenance.select_related('org','asset').order_by('year','id');model=Maintenance
        elif section=='costs':
            if not finance:raise PermissionDenied('Ekonomibehörighet krävs.')
            qs=costs.filter(date__year=today.year).select_related('org','work').order_by('-date','id');model=CostEntry
        elif section=='history':
            if not manage:raise PermissionDenied('Historik kräver förvaltar- eller administratörsbehörighet.')
            related=[('asset',Asset.objects.filter(pk__in=ids)),('workorder',works),('schedule',Schedule.objects.filter(org_id=root.org_id,asset_id__in=ids)),('document',documents),('registryentry',RegistryEntry.objects.filter(org_id=root.org_id,asset_id__in=ids)),('workcomment',WorkComment.objects.filter(work__in=works))]
            if finance:related += [('maintenance',Maintenance.objects.filter(org_id=root.org_id,asset_id__in=ids)),('costentry',costs)]
            # UUIDs are stored as text in the audit table. Cast in SQL, not an unbounded Python list.
            from django.db.models.functions import Cast
            from django.db.models import CharField
            where=Q(pk__in=[])
            for entity,qs in related:where|=Q(entity=entity,entity_id__in=qs.annotate(workspace_audit_identifier=Cast('pk',CharField())).values('workspace_audit_identifier'))
            qs=AuditEvent.objects.filter(org_id=root.org_id).filter(where).order_by('-id').values('id','entity','entity_id','action','created_at','actor__username','after')
            pages=WorkspacePages();rows=pages.paginate_queryset(qs,request)
            for row in rows:
                payload=row.pop('after');row['label']=str(payload.get('title') or payload.get('name') or '')[:200]
            return pages.get_paginated_response(rows)
        else:raise ValidationError('Okänd del av fastighetsvyn.')
        q=request.query_params.get('q','').strip()[:200]
        if q:qs=qs.filter(**{('name' if model==Asset else 'description' if model==CostEntry else 'title')+'__icontains':q})
        pages=WorkspacePages();rows=pages.paginate_queryset(qs,request);data=serializer_for(model)(rows,many=True).data
        if model==Maintenance:
            for row,obj in zip(data,rows):row['planned_amount']=str(obj.budget_for())
        return pages.get_paginated_response(data)
