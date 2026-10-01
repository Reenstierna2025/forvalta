import hashlib, json, uuid
from datetime import timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from .models import *

class Conflict(APIException):
    status_code=409
    default_detail='Uppgiften har ändrats. Läs in den senaste versionen innan du sparar.'


def jsonable(value): return json.loads(json.dumps(value, cls=DjangoJSONEncoder))

def record_data(obj):
    return jsonable({f.name: getattr(obj,f.attname) for f in obj._meta.fields if f.name not in ['reporter_email','public_token_hash','encrypted_secret','token_digest','digest','encrypted_api_key','encrypted_result']})

def audit(user, obj, action, before=None):
    return AuditEvent.objects.create(org_id=obj.id if isinstance(obj,OrgUnit) else getattr(obj,'org_id',None), actor=user if user and user.is_authenticated else None, entity=obj._meta.model_name, entity_id=str(obj.pk), action=action, before=before or {}, after=record_data(obj))

def number():
    Counter.objects.get_or_create(name='work')
    c=Counter.objects.select_for_update().get(name='work'); c.value+=1; c.save()
    return c.value


def mutation(request, callback, fingerprint_extra=''):
    try: key=uuid.UUID(request.headers.get('Idempotency-Key',''))
    except (ValueError,TypeError): raise ValidationError({'detail':'Idempotency-Key krävs för säker sparning.'})
    # One lock per user serializes retries before consulting the unique receipt.
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    from .security import assert_current_session
    assert_current_session(request)
    payload={k:v for k,v in request.data.items() if k!='file'}
    digest=hashlib.sha256((request.path+request.method+json.dumps(payload,sort_keys=True,default=str)+fingerprint_extra).encode()).hexdigest()
    prior=MutationReceipt.objects.filter(user=request.user,key=key).first()
    if prior:
        if prior.fingerprint!=digest: raise Conflict('Sparnyckeln har redan använts för andra uppgifter.')
        return prior.response,prior.status
    result,status=callback()
    result=jsonable(result)
    MutationReceipt.objects.create(user=request.user,key=key,fingerprint=digest,response=result,status=status)
    return result,status


def check_version(request,obj):
    if str(request.data.get('version',''))!=str(obj.version): raise Conflict()


def next_occurrence(schedule, after):
    if schedule.unit in ['day','week']:
        days=schedule.interval*(7 if schedule.unit=='week' else 1)
        periods=(after-schedule.anchor_date).days//days+1
        return schedule.anchor_date+timedelta(days=periods*days)
    months=schedule.interval*(12 if schedule.unit=='year' else 1)
    distance=(after.year-schedule.anchor_date.year)*12+after.month-schedule.anchor_date.month
    n=max(0,distance//months)
    while schedule.anchor_date+relativedelta(months=n*months)<=after: n+=1
    return schedule.anchor_date+relativedelta(months=n*months)

@transaction.atomic

def generate_schedule(schedule_id, until=None):
    s=Schedule.objects.select_for_update().get(id=schedule_id)
    until=until or timezone.localdate()
    count=0
    while not s.archived and s.next_date<=until and count<500:
        work,created=WorkOrder.objects.get_or_create(schedule=s,occurrence=s.next_date,defaults={'org':s.org,'asset':s.asset,'number':number(),'title':s.title,'kind':s.kind,'category':s.category,'due_date':s.next_date,'assigned_to':s.assigned_to,'checklist':s.checklist,'source':'schedule'})
        if created: audit(None,work,'generated')
        s.next_date=next_occurrence(s,s.next_date); count+=1
    if count:
        s.version+=1; s.save(); audit(None,s,'schedule_advanced')
    return count


def validate_reading(obj):
    if obj.meter.org_id!=obj.org_id: raise ValidationError({'meter':'Fel organisationsenhet.'})
    prev=Reading.objects.filter(meter=obj.meter,date__lt=obj.date).order_by('-date').first()
    if Reading.objects.filter(meter=obj.meter,date__gt=obj.date).exists():
        raise ValidationError({'date':'Historisk insättning kräver en separat rättelseprocess. Registrera efter senaste avläsningen.'})
    if obj.replacement:
        if obj.old_final is None or obj.new_initial is None or not obj.serial: raise ValidationError({'replacement':'Mätarbyte kräver slutvärde, startvärde och nytt serienummer.'})
        if prev and obj.old_final<prev.value: raise ValidationError({'old_final':'Slutvärdet är lägre än föregående avläsning.'})
        if obj.value<obj.new_initial: raise ValidationError({'value':'Värdet är lägre än den nya mätarens startvärde.'})
    elif prev and obj.value<prev.value: raise ValidationError({'value':'Värdet har minskat. Registrera mätarbyte om mätaren bytts.'})


def enqueue(kind,payload,key):
    return Job.objects.get_or_create(dedupe_key=key,defaults={'kind':kind,'payload':jsonable(payload),'run_after':timezone.now()})[0]
