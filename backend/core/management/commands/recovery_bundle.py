import json,sys,os
from pathlib import Path
from datetime import datetime,timezone
from django.core.management.base import BaseCommand,CommandError
from core.backup import Repository,stage,commit,completed,verify,restore_local,restore_s3
class Command(BaseCommand):
    help='Operations-only encrypted document/configuration bundles; no API endpoint.'
    def add_arguments(self,p):
        p.add_argument('action',choices=['stage','commit','verify','restore','health','describe','restore-s3'])
        p.add_argument('--id');p.add_argument('--target');p.add_argument('--include-config',action='store_true')
        p.add_argument('--max-age',type=int,default=900)
    def handle(self,*args,**o):
        try:
            repo=Repository();action=o['action']
            if action=='stage':
                meta=json.loads(sys.stdin.read());manifest=stage(repo,meta,Path(os.environ['BACKUP_CONFIG_FILE']).read_bytes());result={'id':manifest['id'],'documents':len(manifest['documents'])}
            elif action=='commit':
                manifest=commit(repo,o['id']);result={'id':manifest['id'],'complete':True,'checkpoint':manifest['checkpoint']}
            else:
                manifest=completed(repo,o['id'])
                if action=='restore':
                    if not o['target']:raise ValueError('An empty target directory is required')
                    result=restore_local(repo,manifest,o['target'],o['include_config'])
                elif action=='restore-s3':result=restore_s3(repo,manifest)
                elif action=='describe':result={'id':manifest['id'],'checkpoint':manifest['checkpoint'],'documents':len(manifest['documents'])}
                elif action=='verify':result={'id':manifest['id'],'verified_documents':verify(repo,manifest)}
                else:
                    age=(datetime.now(timezone.utc)-datetime.fromisoformat(manifest['checkpoint']['time'])).total_seconds()
                    if age>o['max_age'] or age<0:raise ValueError('Last complete database/document checkpoint is stale')
                    result={'id':manifest['id'],'checkpoint_age_seconds':round(age),'status':'ok'}
            self.stdout.write(json.dumps(result))
        except Exception as e:
            # Credentials/configuration must never be printed on a failed storage call.
            raise CommandError('Recovery bundle failed: '+type(e).__name__) from None
