from decimal import Decimal
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .services import jsonable
FIELDS=['Åtgärd','Objekt','Organisation','År','Mängd','Enhet','À-pris','Kostnadsfaktor','Index %','Prisår','Budget','Möjlig finansiering','Beviljad finansiering','Kontering']
NUMBERS={'Mängd','À-pris','Kostnadsfaktor','Index %','Budget','Möjlig finansiering','Beviljad finansiering'}

def compare_scenarios(left,right):
    if (left.org_id,left.start_year,left.years)!=(right.org_id,right.start_year,right.years) or {str(x['id']) for x in left.org_snapshot}!={str(x['id']) for x in right.org_snapshot}:
        raise ValidationError('Jämför versioner med samma organisationsomfång, startår och antal år.')
    def indexed(lines):
        result={}
        for row in lines:
            key=row.get('line_key') or str(row['id'])+':'+str(row['År'])
            if key in result:raise ValidationError('Versionen saknar entydiga radidentiteter. Skapa en ny kopia med stabila radnycklar.')
            result[key]=row
        return result
    a=indexed(left.lines);b=indexed(right.lines);rows=[];details=[]
    def value(row,field):
        v=row.get(field) if row else None
        return Decimal(str(v)) if field in NUMBERS and v is not None else v
    for key in sorted(set(a)|set(b)):
        before=a.get(key);after=b.get(key)
        changes=[field for field in FIELDS if value(before,field)!=value(after,field)]
        state='Tillagd' if before is None else 'Borttagen' if after is None else 'Ändrad' if changes else 'Oförändrad'
        old=Decimal(before['Budget']) if before else Decimal(0);new=Decimal(after['Budget']) if after else Decimal(0)
        rows.append({'id':key,'Åtgärd':(after or before).get('Åtgärd'),'Objekt':(after or before).get('Objekt'),'Förändring':state,'År före':before.get('År') if before else None,'År efter':after.get('År') if after else None,'Budget före':str(old) if before else None,'Budget efter':str(new) if after else None,'Skillnad SEK':str(new-old),'Ändrade fält':', '.join(changes) or None})
        for field in FIELDS:
            rows[-1].setdefault(field+' före',before.get(field) if before else None)
            rows[-1].setdefault(field+' efter',after.get(field) if after else None)
        details.append({'id':key,'changes':[{'field':f,'before':before.get(f) if before else None,'after':after.get(f) if after else None} for f in changes]})
    def total(lines):return sum((Decimal(r['Budget']) for r in lines),Decimal('0.00'))
    old=total(left.lines);new=total(right.lines)
    per_year=[]
    for year in range(left.start_year,left.start_year+left.years):
        x=total([r for r in left.lines if r['År']==year]);y=total([r for r in right.lines if r['År']==year]);per_year.append({'year':year,'before':str(x),'after':str(y),'difference':str(y-x)})
    meta=lambda obj:{'id':str(obj.pk),'name':obj.name,'version':obj.version,'state':obj.state}
    return jsonable({'title':left.name+' → '+right.name,'type':'scenario_comparison','generated_at':timezone.now(),'calculation_version':'scenario-diff-1','filters':{'before':meta(left),'after':meta(right),'start_year':left.start_year,'years':left.years},'definitions':'SEK. Efter minus före, beräknat från respektive sparad versions avrundade budgetrader. Oförändrade rader ingår i totalsummorna. Möjlig och beviljad finansiering jämförs separat som fält. Äldre versioner utan stabila radnycklar matchas efter åtgärds-ID och sparat år; flyttade tillfällen kan då visas som borttagna/tillagda. Ingen version ändras.','totals':{'Före':str(old),'Efter':str(new),'Skillnad':str(new-old)},'per_year':per_year,'rows':rows,'details':details,'count':len(rows)})
