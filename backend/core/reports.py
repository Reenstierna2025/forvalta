from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
import csv, io, json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from xml.sax.saxutils import escape
from django.http import HttpResponse, FileResponse
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from .models import *
from .access import *
from .api import ScopedViewSet, permitted_orgs, checked_id
from .serializers import serializer_for
from .services import *

TYPES={'work':'Arbetsbelastning','overdue':'Försenade arbeten','rounds':'Tillsyn och skötsel','inspections':'Besiktningar','budget':'Underhållsbudget','maintenance':'Underhållsplan','assets':'Fastighetsregister','energy':'Energi och mätvärden','keys':'Nyckelutlåning','registry':'Planer och kontroller','nki':'Nöjd kundindex','invoices':'Fakturaunderlag'}
FINANCIAL={'budget','maintenance','invoices'}
STATUS={'new':'Ny','planned':'Planerad','in_progress':'Pågående','completed':'Kvitterad','verified':'Verifierad','cancelled':'Avbruten'}

def integer(value,default,lo,hi):
    try: result=int(value if value is not None else default)
    except (ValueError,TypeError): raise ValidationError('Ogiltigt år eller intervall.')
    if result<lo or result>hi: raise ValidationError('Värdet ligger utanför tillåtet intervall.')
    return result

def organization_snapshot(ids):
    return list(OrgUnit.objects.filter(id__in=ids).values('id','name','kind','parent_id','version'))

def scoped(user,params,financial=False):
    ids=scope(user,INTERNAL,financial)
    if params.get('org'): ids &= expand(checked_id(params['org']))
    return ids

def filter_assets(qs,params):
    if params.get('asset'): qs=qs.filter(asset_id=checked_id(params['asset']))
    return qs

def build_report(user,kind,params):
    if kind not in TYPES: raise ValidationError('Okänd rapporttyp.')
    ids=scoped(user,params,kind in FINANCIAL)
    if kind in FINANCIAL and not ids: raise PermissionDenied('Ekonomibehörighet krävs.')
    rows=[]; totals={}; definitions=''; today=timezone.localdate()
    dates={}
    for key in ['from','to']:
        if params.get(key):
            try: dates[key]=date.fromisoformat(params[key])
            except (ValueError,TypeError):raise ValidationError('Ogiltigt datum.')
    if dates.get('from') and dates.get('to') and dates['from']>dates['to']:raise ValidationError('Från-datum måste vara före till-datum.')
    if kind in ['work','overdue','rounds','inspections']:
        qs=filter_assets(work_scope(user),params)
        if params.get('org'): qs=qs.filter(org_id__in=expand(checked_id(params['org'])))
        if kind=='overdue': qs=qs.filter(due_date__lt=today).exclude(status__in=['verified','cancelled'])
        if kind in ['rounds','inspections']: qs=qs.filter(kind='round' if kind=='rounds' else 'inspection')
        if params.get('status'): qs=qs.filter(status=params['status'])
        if params.get('category'): qs=qs.filter(category=params['category'])
        if params.get('assigned_to'):
            try: assignee=int(params['assigned_to'])
            except ValueError: raise ValidationError('Ogiltig utförare.')
            qs=qs.filter(assigned_to_id=assignee)
        for field,lookup in [('from','due_date__gte'),('to','due_date__lte')]:
            if params.get(field):
                try: d=date.fromisoformat(params[field])
                except ValueError: raise ValidationError('Ogiltigt datum.')
                qs=qs.filter(**{lookup:d})
        rows=[{'id':str(w.id),'Nummer':w.number,'Rubrik':w.title,'Objekt':w.asset.name,'Organisation':w.org.name,'Status':STATUS[w.status],'Datum':w.due_date.isoformat() if w.due_date else None,'Utförare':w.assigned_to.get_full_name() or w.assigned_to.username if w.assigned_to else None,'Typ':w.kind} for w in qs.select_related('asset','org','assigned_to').order_by('due_date')]
        totals={'Antal':len(rows)}; definitions='Försenat: förfallodatum före dagens datum och varken verifierat eller avbrutet. Kvitterat och verifierat redovisas separat.'
    elif kind in ['budget','maintenance']:
        start=integer(params.get('start_year'),today.year,1900,2200); years=integer(params.get('years'),10,1,30)
        qs=filter_assets(Maintenance.objects.filter(org_id__in=ids,archived=False).select_related('asset','org'),params)
        if params.get('category'): qs=qs.filter(category=params['category'])
        by_year={y:Decimal(0) for y in range(start,start+years)}
        for p in qs:
            occurrence=p.year
            while occurrence<start+years:
                if occurrence>=start:
                    amount=p.budget_for(occurrence); by_year[occurrence]+=amount
                    rows.append({'id':str(p.id),'Åtgärd':p.title,'Objekt':p.asset.name,'Organisation':p.org.name,'År':occurrence,'Mängd':str(p.quantity),'Enhet':p.unit,'À-pris':str(p.unit_price),'Kostnadsfaktor':str(p.cost_factor),'Index %':str(p.index_percent),'Prisår':p.price_year,'Budget':str(amount),'Möjlig finansiering':str(p.funding_possible) if occurrence==p.year else '0.00','Beviljad finansiering':str(p.funding_granted) if occurrence==p.year else '0.00','Kontering':p.account or None})
                if not p.interval_years: break
                occurrence+=p.interval_years
        actual=Decimal(0)
        for c in filter_assets_cost(CostEntry.objects.filter(org_id__in=ids,date__year__gte=start,date__year__lt=start+years),params): actual+=c.total
        totals={'Budget':str(sum(by_year.values(),Decimal(0))),'Utfall':str(actual),'Per år':[{'year':y,'budget':str(v)} for y,v in by_year.items()]}
        definitions='SEK. Budget = mängd × à-pris × kostnadsfaktor × (1 + index/100)^(åtgärdsår − prisår, minst 0). Avrundning per åtgärd till ören, half-up. Utfall omfattar registrerade kostnader i urvalet. Finansiering återkommer inte automatiskt.'
    elif kind=='assets':
        qs=Asset.objects.filter(org_id__in=ids,archived=False).select_related('org')
        if params.get('asset'): qs=qs.filter(pk=checked_id(params['asset']))
        rows=[{'id':str(a.id),'Namn':a.name,'Typ':a.kind,'Organisation':a.org.name,'Adress':a.address or None,'Area m²':str(a.area) if a.area is not None else None} for a in qs]
        totals={'Antal':len(rows)}; definitions='Varje registerobjekt räknas en gång. Saknad area visas som saknad, inte noll.'
    elif kind=='keys':
        loans=KeyLoan.objects.filter(org_id__in=ids).select_related('key','key__asset')
        if params.get('asset'): loans=loans.filter(key__asset_id=checked_id(params['asset']))
        if dates.get('from'):loans=loans.filter(due_date__gte=dates['from'])
        if dates.get('to'):loans=loans.filter(due_date__lte=dates['to'])
        rows=[{'id':str(l.id),'Nyckel':l.key.name,'Objekt':l.key.asset.name,'Låntagare':l.borrower,'Åter senast':l.due_date.isoformat(),'Återlämnad':l.returned_at.isoformat() if l.returned_at else None} for l in loans]
        totals={'Utlånade':sum(1 for r in rows if r['Återlämnad'] is None)}; definitions='Ett aktivt lån per fysisk nyckel.'
    elif kind=='energy':
        meters=filter_assets(Meter.objects.filter(org_id__in=ids,archived=False),params)
        for m in meters.select_related('asset'):
            previous=None
            for r in m.readings.order_by('date'):
                consumption=None
                if previous:
                    consumption=(r.old_final-previous.value+r.value-r.new_initial) if r.replacement else r.value-previous.value
                include=(not dates.get('from') or r.date>=dates['from']) and (not dates.get('to') or r.date<=dates['to'])
                if include: rows.append({'id':str(r.id),'Mätare':m.name,'Objekt':m.asset.name,'Datum':r.date.isoformat(),'Mätarställning':str(r.value),'Förbrukning':str(consumption) if consumption is not None else None,'Enhet':m.unit,'Mätarbyte':'Ja' if r.replacement else 'Nej'})
                previous=r
        definitions='Förbrukning mellan två avläsningar, med slut- och startvärden vid mätarbyte. Första avläsningen saknar jämförelse. Olika enheter summeras inte.'
    elif kind in ['registry','nki']:
        qs=filter_assets(RegistryEntry.objects.filter(org_id__in=ids,archived=False),params).select_related('asset')
        if kind=='nki': qs=qs.filter(kind='nki')
        if dates.get('from'):qs=qs.filter(due_date__gte=dates['from'])
        if dates.get('to'):qs=qs.filter(due_date__lte=dates['to'])
        rows=[{'id':str(r.id),'Namn':r.title,'Objekt':r.asset.name,'Typ':r.kind,'Datum':r.due_date.isoformat() if r.due_date else None,'Status':r.state,'Betyg':r.score} for r in qs]
        scores=[r['Betyg'] for r in rows if r['Betyg'] is not None]
        totals={'Antal':len(rows),'Medelbetyg':str((sum(Decimal(x) for x in scores)/len(scores)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) if scores else None}
        definitions='Betyg 0–10. Medelvärde av registrerade svar; detta är inte en verifierad kopia av DeDus NKI-formel.'
    elif kind=='invoices':
        costs=filter_assets_cost(CostEntry.objects.filter(org_id__in=ids).select_related('work','org'),params)
        rows=[{'id':str(c.id),'Order':c.work.number,'Beskrivning':c.description,'Typ':c.kind,'Datum':c.date.isoformat(),'Antal':str(c.quantity),'À-pris':str(c.unit_price),'Belopp':str(c.total)} for c in costs]
        totals={'Belopp':str(sum((Decimal(r['Belopp']) for r in rows),Decimal(0)))}; definitions='Registrerade tids-, material- och kostnadsposter i SEK. Underlag för granskning, inte bokförd faktura.'
    from .report_analysis import aggregate
    analysis=aggregate(kind,rows,params)
    detail_rows=rows if analysis else None
    if analysis:
        rows=analysis['groups'];definitions+=' '+analysis['definition']
    allowed_columns=params.get('columns')
    if allowed_columns:
        columns=allowed_columns if isinstance(allowed_columns,list) else str(allowed_columns).split(',')
        all_columns=set().union(*(r.keys() for r in rows)) if rows else set(columns)
        if any(c not in all_columns for c in columns): raise ValidationError('Okänd rapportkolumn.')
        rows=[{k:v for k,v in r.items() if k in columns or k=='id'} for r in rows]
    return jsonable({'title':TYPES[kind],'type':kind,'generated_at':timezone.now(),'filters':dict(params),'calculation_version':'1.1','definitions':definitions,'totals':totals,'rows':rows,'count':len(rows),'analysis':analysis,'detail_rows':detail_rows})

def filter_assets_cost(qs,params):
    if params.get('asset'): qs=qs.filter(work__asset_id=checked_id(params['asset']))
    for field,lookup in [('from','date__gte'),('to','date__lte')]:
        if params.get(field):
            try: d=date.fromisoformat(params[field])
            except ValueError: raise ValidationError('Ogiltigt datum.')
            qs=qs.filter(**{lookup:d})
    return qs

def safe_cell(v):
    if v is None: return 'Saknas'
    if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')): return "'"+v
    return v

def export_report(data,fmt):
    rows=data['rows']; columns=[x for x in rows[0] if x!='id'] if rows else ['Inga poster']
    numeric={'Budget','Utfall','À-pris','Belopp','Mängd','Kostnadsfaktor','Index %','Möjlig finansiering','Beviljad finansiering','Area m²','Mätarställning','Förbrukning','Antal','Värde','Poster','Saknade värden','Skillnad SEK','År','Prisår'}
    numeric |= {c+suffix for c in list(numeric) for suffix in [' före',' efter']}
    def cell(row,c):return Decimal(str(row[c])) if c in numeric and row.get(c) is not None else safe_cell(row.get(c))
    if fmt=='csv':
        stream=io.StringIO(); writer=csv.writer(stream,delimiter=';'); meta_columns=['Rapport','Urval','Genererad','Beräkningsversion','Måttdefinition']
        meta_values=[data['title'],json.dumps(data['filters'],ensure_ascii=False),data['generated_at'],data['calculation_version'],data['definitions']]
        writer.writerow(columns+meta_columns)
        for row in rows: writer.writerow([cell(row,c) for c in columns]+[safe_cell(v) for v in meta_values])
        response=HttpResponse('\ufeff'+stream.getvalue(),content_type='text/csv; charset=utf-8'); response['Content-Disposition']='attachment; filename="rapport.csv"'; return response
    output=io.BytesIO()
    if fmt=='xlsx':
        wb=Workbook(); ws=wb.active; ws.title='Rapport'; ws.append(columns)
        for row in rows: ws.append([cell(row,c) for c in columns])
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
        for col in ws.columns: ws.column_dimensions[col[0].column_letter].width=min(45,max(15,max(len(str(c.value or '')) for c in col)+2))
        meta=wb.create_sheet('Definition och urval')
        for key in ['title','generated_at','filters','calculation_version','definitions']: meta.append([key,json.dumps(data[key],ensure_ascii=False) if isinstance(data[key],dict) else data[key]])
        wb.save(output); mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt=='pdf':
        styles=getSampleStyleSheet(); story=[Paragraph(escape(data['title']),styles['Title']),Paragraph(escape(data['definitions']),styles['Normal']),Spacer(1,10),Paragraph(escape(str(data['generated_at'])),styles['Normal']),Paragraph(escape(json.dumps(data['filters'],ensure_ascii=False)),styles['Normal']),Spacer(1,12)]
        for key,value in data['totals'].items():
            if not isinstance(value,list):story.append(Paragraph(escape(key)+': '+escape(str(value if value is not None else 'Saknas')),styles['Normal']))
        # Vertical records preserve all fields without shrinking wide tables to unreadable text.
        for index,row in enumerate(rows):
            story.append(Paragraph(str(index+1)+'. '+escape(str(next(iter({k:v for k,v in row.items() if k!='id'}.values()),''))),styles['Heading3']))
            cells=[[Paragraph(escape(c),styles['Normal']),Paragraph(escape(str(row.get(c) if row.get(c) is not None else 'Saknas')),styles['Normal'])] for c in columns]
            table=Table(cells,colWidths=[150,350]); table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.25,colors.HexColor('#dde3e9')),('BOTTOMPADDING',(0,0),(-1,-1),6)])); story.append(table)
        if not rows: story.append(Paragraph('Inga poster i urvalet.',styles['Normal']))
        SimpleDocTemplate(output,pagesize=A4,rightMargin=40,leftMargin=40).build(story); mime='application/pdf'
    else: raise ValidationError('Välj csv, xlsx eller pdf.')
    output.seek(0); return FileResponse(output,as_attachment=True,filename='rapport.'+fmt,content_type=mime)

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class ReportsView(APIView):
    def get(self,request):
        kind=request.query_params.get('type','work')
        data=build_report(request.user,kind,request.query_params.dict())
        if request.query_params.get('format_file'): return export_report(data,request.query_params['format_file'])
        return Response(data)
    @transaction.atomic
    def post(self,request):
        def save():
            kind=request.data.get('type','work'); params=request.data.get('filters',{})
            data=build_report(request.user,kind,params); ids=scoped(request.user,params,kind in FINANCIAL)
            if not ids: raise PermissionDenied('Du saknar behörighet att arkivera rapporten.')
            org_id=checked_id(params['org']) if params.get('org') else sorted(ids,key=str)[0]
            require(request.user,org_id,MANAGE,kind in FINANCIAL)
            obj=ReportSnapshot.objects.create(org_id=org_id,title=request.data.get('title') or data['title'],report_type=kind,filters=params,data=data,organization_snapshot=jsonable(organization_snapshot(ids)),included_org_ids=[str(x) for x in ids],financial=kind in FINANCIAL,generated_by=request.user)
            audit(request.user,obj,'report_archived'); return {'id':obj.id,'version':obj.version},201
        result,code=mutation(request,save); return Response(result,status=code)

class SnapshotViewSet(ScopedViewSet):
    model=ReportSnapshot; serializer_class=serializer_for(ReportSnapshot); http_method_names=['get','head','options']
    def get_queryset(self):
        base=super().get_queryset(); ids={str(x) for x in scope(self.request.user,INTERNAL)}; finance={str(x) for x in scope(self.request.user,INTERNAL,True)}
        permitted=[o.id for o in base.select_related(None).only('id','included_org_ids','financial') if set(o.included_org_ids)<=(finance if o.financial else ids)]
        return base.filter(pk__in=permitted)
    @action(detail=True,methods=['get'])
    def export(self,request,pk=None): return export_report(self.get_object().data,request.query_params.get('format_file','pdf'))

class ScenarioViewSet(ScopedViewSet):
    model=BudgetScenario; serializer_class=serializer_for(BudgetScenario); financial=True; manage=True; immutable=True
    def before_save(self,obj,created):
        if created:
            data=build_report(self.request.user,'budget',{'org':str(obj.org_id),'start_year':obj.start_year,'years':obj.years})
            obj.lines=data['rows']
            for line in obj.lines:line['line_key']=str(line['id'])+':'+str(line['År'])
            obj.org_snapshot=jsonable(organization_snapshot(scoped(self.request.user,{'org':str(obj.org_id)},True)))
    def get_queryset(self):
        base=super().get_queryset(); allowed={str(x) for x in scope(self.request.user,INTERNAL,True)}
        return base.filter(pk__in=[s.pk for s in base if {str(x['id']) for x in s.org_snapshot}<=allowed])
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def clone(self,request,pk=None):
        import copy
        def save():
            source=self.get_queryset().select_for_update(of=('self',)).get(pk=pk);self.check_write(source);check_version(request,source)
            name=str(request.data.get('name','')).strip()
            if not name or len(name)>180:raise ValidationError('Ange ett namn på högst 180 tecken.')
            lines=copy.deepcopy(source.lines)
            for line in lines:line.setdefault('line_key',str(line['id'])+':'+str(line['År']))
            obj=BudgetScenario.objects.create(org=source.org,name=name,start_year=source.start_year,years=source.years,lines=lines,org_snapshot=source.org_snapshot)
            audit(request.user,obj,'scenario_copied');return {'id':obj.id,'version':obj.version},201
        result,code=mutation(request,save);return Response(result,status=code)

    @action(detail=True,methods=['get'])
    def compare(self,request,pk=None):
        from .scenario_compare import compare_scenarios
        left=self.get_object()
        right=self.get_queryset().filter(pk=checked_id(request.query_params.get('other'))).first()
        if not right:raise NotFound()
        for key,obj in [('before_version',left),('after_version',right)]:
            if request.query_params.get(key) and str(obj.version)!=request.query_params[key]:raise Conflict('Budgetversionen har ändrats. Läs in jämförelsen igen före export.')
        data=compare_scenarios(left,right)
        if request.query_params.get('format_file'):return export_report(data,request.query_params['format_file'])
        return Response(data)

    @action(detail=True,methods=['post'])
    @transaction.atomic
    def revise(self,request,pk=None):
        def save():
            obj=self.get_queryset().select_for_update(of=('self',)).get(pk=pk); self.check_write(obj); check_version(request,obj)
            if obj.state!='draft': raise Conflict('Fastställda budgetversioner är låsta.')
            index=integer(request.data.get('line'),0,0,len(obj.lines)-1); year=integer(request.data.get('year'),obj.start_year,obj.start_year,obj.start_year+obj.years-1)
            before=record_data(obj); line=obj.lines[index]; line['År']=year
            amount=Decimal(line['Mängd'])*Decimal(line['À-pris'])*Decimal(line['Kostnadsfaktor'])*(1+Decimal(line['Index %'])/100)**max(0,year-int(line['Prisår']))
            line['Budget']=str(amount.quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
            obj.version+=1; obj.save(); audit(request.user,obj,'scenario_changed',before); return {'id':obj.id,'version':obj.version},200
        result,code=mutation(request,save); return Response(result,status=code)
    @action(detail=True,methods=['post'])
    @transaction.atomic
    def publish(self,request,pk=None):
        def save():
            obj=self.get_queryset().select_for_update(of=('self',)).get(pk=pk); self.check_write(obj); check_version(request,obj)
            if obj.state=='published': raise Conflict('Budgetversionen är redan fastställd.')
            obj.state='published'; obj.published_at=timezone.now(); obj.version+=1; obj.save(); audit(request.user,obj,'scenario_published'); return {'id':obj.id,'version':obj.version},200
        result,code=mutation(request,save); return Response(result,status=code)

class TemplateViewSet(ScopedViewSet):
    model=ReportTemplate; serializer_class=serializer_for(ReportTemplate); manage=True
    def before_save(self,obj,created):
        if not isinstance(obj.config,dict) or obj.config.get('type') not in TYPES: raise ValidationError('Välj en rapporttyp.')
        build_report(self.request.user,obj.config['type'],obj.config.get('filters',{}))

class SubscriptionViewSet(ScopedViewSet):
    model=Subscription; serializer_class=serializer_for(Subscription); manage=True
    def before_save(self,obj,created):
        if obj.report_type not in TYPES: raise ValidationError('Okänd rapporttyp.')
        financial=obj.report_type in FINANCIAL
        require(self.request.user,obj.org_id,MANAGE,financial)
        if obj.org_id not in scope(obj.recipient,INTERNAL,financial) or not obj.recipient.email: raise ValidationError('Mottagaren behöver behörighet och e-postadress.')
        obj.config={**obj.config,'org':str(obj.org_id)}
