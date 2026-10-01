#!/usr/bin/env python3
"""Host coordinator. Docker CLI only; no Docker socket inside an application container."""
import argparse,datetime,fcntl,json,os,subprocess,sys,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(args,stdin=None):
    p=subprocess.run(['docker','compose',*args],cwd=ROOT,input=stdin,text=True,capture_output=True)
    if p.returncode:raise RuntimeError('Operation failed: '+str(args[0]))
    return p.stdout.strip()

def sql(statement):return run(['exec','-T','--user','postgres','db','psql','-U','postgres','-d','forvalta','-At','-v','ON_ERROR_STOP=1','-c',statement])
def backrest(*args):return run(['exec','-T','--user','postgres','db','pgbackrest','--stanza=forvalta',*args])
def bundle(action,*args,stdin=None):return json.loads(run(['run','--rm','-T','--no-deps','recovery','python','manage.py','recovery_bundle',action,*args],stdin))

def checkpoint():
    info=json.loads(backrest('--output=json','info'))[0]
    backups=[b for b in info.get('backup',[]) if not b.get('error')]
    if not backups:raise RuntimeError('A completed PostgreSQL base backup is required')
    latest=max(backups,key=lambda b:b['timestamp']['stop'])
    if datetime.datetime.now(datetime.timezone.utc).timestamp()-latest['timestamp']['stop']>26*3600:raise RuntimeError('Database backup is too old')
    name='forvalta_'+uuid.uuid4().hex
    # PostgreSQL marker precedes the document listing. Never reverse this ordering.
    meta=json.loads(sql("WITH t AS MATERIALIZED (SELECT clock_timestamp() AS moment), p AS MATERIALIZED (SELECT moment,pg_create_restore_point('"+name+"') AS lsn FROM t) SELECT json_build_object('name','"+name+"','lsn',lsn::text,'wal',pg_walfile_name(lsn),'time',moment,'system_identifier',(pg_control_system()).system_identifier::text) FROM p"))
    meta['base_backup']=latest['label']
    staged=bundle('stage',stdin=json.dumps(meta))
    sql('SELECT pg_switch_wal()');backrest('check')
    # Check alone confirms current archiving; explicitly retrieve the marker segment too.
    path='/tmp/forvalta-wal-'+uuid.uuid4().hex
    try:backrest('archive-get',meta['wal'],path)
    finally:run(['exec','-T','--user','postgres','db','rm','-f',path])
    return bundle('commit','--id',staged['id'])

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['checkpoint','health','verify']);p.add_argument('--id');a=p.parse_args()
    state=ROOT/'backups';state.mkdir(mode=0o700,exist_ok=True)
    with open(state/'coordinator.lock','a') as lock:
        if a.action=='checkpoint':fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            if a.action=='checkpoint':result=checkpoint()
            elif a.action=='verify':result=bundle('verify',*(['--id',a.id] if a.id else []))
            else:
                result=bundle('health')
                run(['exec','-T','api','python','manage.py','ops_health'])
                disk=run(['exec','-T','db','df','-Pk','/var/lib/postgresql']).splitlines()[-1].split()
                if int(disk[4].strip('%'))>80:raise RuntimeError('Database disk low')
                archive=json.loads(sql("SELECT json_build_object('last_failed',last_failed_time,'last_success',last_archived_time,'free_check',true) FROM pg_stat_archiver"))
                if archive['last_failed'] and (not archive['last_success'] or archive['last_failed']>archive['last_success']):raise RuntimeError('WAL archive failure')
                info=json.loads(backrest('--output=json','info'))[0]
                newest=max(b['timestamp']['stop'] for b in info.get('backup',[]) if not b.get('error'))
                if datetime.datetime.now(datetime.timezone.utc).timestamp()-newest>26*3600:raise RuntimeError('Database backup is stale')
            print(json.dumps(result));return 0
        except Exception as e:
            print(json.dumps({'status':'failed','operation':a.action,'error':type(e).__name__}),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
