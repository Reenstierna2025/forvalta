"""Allowlisted report aggregation; no user-defined formulas or executable queries."""
from decimal import Decimal
from rest_framework.exceptions import ValidationError

GROUPS={
 'work':['Organisation','Objekt','Status','Utförare','Typ'],
 'overdue':['Organisation','Objekt','Status','Utförare','Typ'],
 'rounds':['Organisation','Objekt','Status','Utförare'],
 'inspections':['Organisation','Objekt','Status','Utförare'],
 'budget':['Organisation','Objekt','År','Kontering'],
 'maintenance':['Organisation','Objekt','År','Kontering'],
 'assets':['Organisation','Typ'],
 'invoices':['Typ','Datum'],
 'registry':['Objekt','Typ','Status'],
 'nki':['Objekt','Status'],
 'keys':['Objekt'],
 'energy':['Objekt','Mätare','Enhet'],
}
MEASURES={kind:['Antal'] for kind in GROUPS}
for kind in ['budget','maintenance']:MEASURES[kind]+=['Budget','Möjlig finansiering','Beviljad finansiering']
MEASURES['invoices']+=['Belopp']

def aggregate(kind,rows,params):
    group=params.get('group_by')
    if not group:return None
    measure=params.get('measure','Antal')
    if group not in GROUPS[kind] or measure not in MEASURES[kind]:raise ValidationError('Otillåten gruppering eller mått för rapporttypen.')
    buckets={}
    for i,row in enumerate(rows):
        value=row.get(group);key=(type(value).__name__,str(value))
        b=buckets.setdefault(key,{'label':value,'indices':[],'amount':Decimal(0),'missing':0})
        b['indices'].append(i)
        if measure=='Antal':b['amount']+=1
        elif row.get(measure) is None:b['missing']+=1
        else:b['amount']+=Decimal(str(row[measure]))
    groups=[]
    for i,b in enumerate(sorted(buckets.values(),key=lambda b:(b['label'] is None,str(b['label'])))):
        groups.append({'id':str(i),'Grupp':b['label'],'Värde':None if b['missing']==len(b['indices']) else str(b['amount']),'Poster':len(b['indices']),'Saknade värden':b['missing']})
    order=sorted(buckets.values(),key=lambda b:(b['label'] is None,str(b['label'])))
    return {'group_by':group,'measure':measure,'unit':'poster' if measure=='Antal' else 'SEK','groups':groups,'members':{str(i):b['indices'] for i,b in enumerate(order)},'definition':f'Gruppering efter {group}. '+('Antal rapportposter; återkommande underhåll räknas en gång per redovisat tillfälle.' if measure=='Antal' else f'Summa av {measure} från redan beräknade och avrundade underlagsrader. Saknade värden räknas separat; en helt saknad summa är null.')}
