#!/usr/bin/env python3
"""Automatic PITR + attachment drill; unique volumes, no web ports, no mail worker."""
import datetime,json,os,subprocess,sys,time,uuid
from recovery import ROOT,bundle,run

def main():
    start=time.monotonic();manifest=bundle('describe');point=manifest['checkpoint']
    project='forvalta-drill-'+uuid.uuid4().hex
    env=dict(os.environ,DRILL_DB_IMAGE=run(['images','-q','db']).splitlines()[0],DRILL_API_IMAGE=run(['images','-q','api']).splitlines()[0])
    def drill(*args):
        p=subprocess.run(['docker','compose','--env-file',str(ROOT/'.env'),'-f',str(ROOT/'deploy/compose.drill.yaml'),'-p',project,*args],cwd=ROOT,env=env,text=True,capture_output=True,timeout=14000)
        if p.returncode:raise RuntimeError('Isolated restore operation failed')
        return p.stdout.strip()
    result={'project':project,'backup_id':manifest['id'],'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'failed'}
    try:
        drill('run','--rm','-T','--no-deps','--user','root','db','install','-d','-o','postgres','-g','postgres','-m','0700','/var/lib/postgresql/18/docker')
        drill('run','--rm','-T','--no-deps','--user','postgres','db','pgbackrest','--stanza=forvalta','--set='+point['base_backup'],'--type=name','--target='+point['name'],'--target-action=promote','--archive-mode=off','restore')
        drill('up','-d','--wait','--wait-timeout','900','db')
        # pg_isready can report ready during hot standby. Require promotion at target.
        ready=drill('exec','-T','--user','postgres','db','psql','-U','postgres','-d','forvalta','-At','-c','SELECT NOT pg_is_in_recovery()')
        while ready!='t':
            if time.monotonic()-start>14000:raise RuntimeError('Recovery target has not been reached')
            time.sleep(5)
            ready=drill('exec','-T','--user','postgres','db','psql','-U','postgres','-d','forvalta','-At','-c','SELECT NOT pg_is_in_recovery()')
        drill('run','--rm','-T','--no-deps','--user','root','api','sh','-c','chown 10001:10001 /restore && chmod 700 /restore')
        drill('run','--rm','-T','--no-deps','api','python','manage.py','recovery_bundle','restore','--id',manifest['id'],'--target','/restore/media')
        result['integrity']=json.loads(drill('run','--rm','-T','--no-deps','api','python','manage.py','verify_integrity'))
        result['restore_seconds']=round(time.monotonic()-start,2)
        result['checkpoint_age_at_start_seconds']=round((datetime.datetime.fromisoformat(result['started_at'])-datetime.datetime.fromisoformat(point['time'])).total_seconds(),2)
        result['rto_pass']=result['restore_seconds']<=14400
        result['rpo_pass']=0<=result['checkpoint_age_at_start_seconds']<=900
        result['status']='ok' if result['rto_pass'] and result['rpo_pass'] else 'failed'
    except Exception as exc:result['error']=type(exc).__name__
    finally:
        try:drill('down','--volumes','--remove-orphans')
        except Exception:result['cleanup_required']=project;result['status']='failed'
        path=ROOT/'backups';path.mkdir(mode=0o700,exist_ok=True)
        target=path/('drill-'+project+'.json');target.write_text(json.dumps(result,indent=2));os.chmod(target,0o600)
    print(json.dumps(result));return 0 if result['status']=='ok' else 1
if __name__=='__main__':sys.exit(main())
