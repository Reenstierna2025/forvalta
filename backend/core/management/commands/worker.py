import hashlib,hmac,time
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from core.models import Job,Schedule,Subscription,WorkOrder,OrgUnit,ReportSnapshot,Counter
from core.services import generate_schedule,enqueue,audit,jsonable
from core.reports import build_report,scoped,organization_snapshot,FINANCIAL
from core.access import scope,INTERNAL


def process_job(job):
    if job.kind in ['status_email','public_receipt']:
        w=WorkOrder.objects.get(pk=job.payload['work'])
        if not w.reporter_email: return
        body=f'Ärende #{w.number}: din felanmälan har tagits emot.' if job.kind=='public_receipt' else f'Ärende #{w.number} har uppdaterats. Använd din tidigare ärendelänk för att läsa återkopplingen.'
        if job.kind=='public_receipt':
            token=hmac.new(settings.SECRET_KEY.encode(),('public:'+job.payload['receipt_key']).encode(),hashlib.sha256).hexdigest()
            body+='\n'+settings.PUBLIC_ORIGIN+'/#/track/'+token
        send_mail(f'Förvalta · ärende #{w.number}',body,settings.DEFAULT_FROM_EMAIL,[w.reporter_email])
    elif job.kind=='report_email':
        sub=Subscription.objects.select_related('recipient').get(pk=job.payload['subscription'])
        if sub.archived or not sub.recipient.is_active: return
        financial=sub.report_type in FINANCIAL
        if sub.org_id not in scope(sub.recipient,INTERNAL,financial):
            raise PermissionError('Recipient no longer has report access')
        # Recheck scope at execution time; e-mail contains only a protected link.
        data=build_report(sub.recipient,sub.report_type,sub.config)
        ids=scoped(sub.recipient,sub.config,financial)
        with transaction.atomic():
            locked_job=Job.objects.select_for_update().get(pk=job.pk)
            if not locked_job.payload.get('snapshot'):
                snap=ReportSnapshot.objects.create(org=sub.org,title=sub.name,report_type=sub.report_type,filters=sub.config,data=data,organization_snapshot=jsonable(organization_snapshot(ids)),included_org_ids=[str(i) for i in ids],financial=financial,generated_by=sub.recipient)
                audit(sub.recipient,snap,'scheduled_report')
                locked_job.payload={**locked_job.payload,'snapshot':str(snap.id)};locked_job.save(update_fields=['payload'])
        send_mail('Förvalta · '+sub.name,'En rapport finns i rapportarkivet. Logga in för att läsa den:\n'+settings.PUBLIC_ORIGIN+'/#/reports',settings.DEFAULT_FROM_EMAIL,[sub.recipient.email])
    else: raise ValueError('Unknown job kind')


def schedule_due():
    for id in Schedule.objects.filter(archived=False,next_date__lte=timezone.localdate()).values_list('id',flat=True): generate_schedule(id)
    for id in Subscription.objects.filter(archived=False,next_date__lte=timezone.localdate()).values_list('id',flat=True):
        with transaction.atomic():
            sub=Subscription.objects.select_for_update().get(pk=id)
            if sub.next_date>timezone.localdate(): continue
            enqueue('report_email',{'subscription':str(sub.id)},f'subscription:{sub.id}:{sub.next_date}')
            while sub.next_date<=timezone.localdate(): sub.next_date+=timedelta(days=sub.interval_days)
            sub.version+=1;sub.save()


def run_one():
    with transaction.atomic():
        now=timezone.now()
        Job.objects.filter(status='running',locked_at__lt=now-timedelta(minutes=15)).update(status='pending')
        j=Job.objects.select_for_update(skip_locked=True).filter(status='pending',run_after__lte=now).order_by('run_after').first()
        if not j:return False
        j.status='running';j.locked_at=now;j.attempts+=1;j.save()
    try:
        process_job(j)
        Job.objects.filter(pk=j.pk).update(status='done',last_error='')
    except Exception as exc:
        Job.objects.filter(pk=j.pk).update(status='failed' if j.attempts>=5 else 'pending',last_error=type(exc).__name__,run_after=timezone.now()+timedelta(minutes=2**j.attempts))
    return True

class Command(BaseCommand):
    help='Durable scheduled work and notification worker'
    def add_arguments(self,parser):parser.add_argument('--once',action='store_true')
    def handle(self,*args,**options):
        while True:
            Counter.objects.update_or_create(name='worker_heartbeat',defaults={'value':int(time.time())})
            schedule_due()
            while run_one():pass
            if options['once']:return
            time.sleep(30)
