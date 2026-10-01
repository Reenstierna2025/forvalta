import json,time,shutil
from datetime import timedelta
from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from core.models import Counter,Job
class Command(BaseCommand):
    help='Health checks for monitoring. Exits nonzero on failure; never sends mail.'
    def handle(self,*args,**options):
        errors=[];heartbeat=Counter.objects.filter(name='worker_heartbeat').first()
        if not heartbeat or time.time()-heartbeat.value>120:errors.append('worker_heartbeat_stale')
        if Job.objects.filter(status='failed').exists():errors.append('failed_background_jobs')
        if Job.objects.filter(status='pending',run_after__lt=timezone.now()-timedelta(minutes=30)).exists():errors.append('job_queue_stale')
        disk=shutil.disk_usage('/')
        if disk.free/disk.total<.20:errors.append('application_disk_low')
        self.stdout.write(json.dumps({'status':'failed' if errors else 'ok','errors':errors}))
        if errors:raise CommandError('Operations check failed')
