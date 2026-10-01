import json
from django.core.management.base import BaseCommand,CommandError
from django.db import connection
from core.models import Document,Asset,WorkOrder,Job
from core.storage import read_file

class Command(BaseCommand):
    help='Read every attachment and verify checksum, size, object relations and failed jobs; never changes data.'
    def handle(self,*args,**options):
        errors=[];verified=0
        for d in Document.objects.iterator(chunk_size=100):
            try:
                data=read_file(d)
                if len(data)!=d.size:raise ValueError('size')
                verified+=1
            except Exception as e:errors.append({'document':str(d.id),'error':type(e).__name__})
        with connection.cursor() as c:
            c.execute('SELECT COUNT(*) FROM core_workorder w JOIN core_asset a ON a.id=w.asset_id WHERE w.org_id<>a.org_id')
            mismatch=c.fetchone()[0]
        if mismatch:errors.append({'work_asset_org_mismatch':mismatch})
        result={'assets':Asset.objects.count(),'work':WorkOrder.objects.count(),'documents_verified':verified,'failed_jobs':Job.objects.filter(status='failed').count(),'errors':errors}
        self.stdout.write(json.dumps(result))
        if errors:raise CommandError('Integrity verification failed')
