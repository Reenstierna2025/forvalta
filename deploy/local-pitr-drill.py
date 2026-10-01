#!/usr/bin/env python3
"""Reproducible native PostgreSQL PITR test, synthetic data only.
Run with the project's virtualenv Python; requires PostgreSQL 18 binaries.
Creates isolated clusters, encrypted base backup/WAL and document bundles.
Does not touch the application's database or any external account.
"""
import argparse,datetime,io,json,os,secrets,shlex,shutil,subprocess,sys,tarfile,time,uuid
from pathlib import Path
import psycopg
from cryptography.fernet import Fernet,InvalidToken
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pg-bin',required=True);parser.add_argument('--work-dir',required=True);parser.add_argument('--result',required=True);parser.add_argument('--primary-port',type=int,default=55436);parser.add_argument('--restore-port',type=int,default=55437);a=parser.parse_args()
    root=Path(a.work_dir).resolve()/('pitr-'+uuid.uuid4().hex);root.mkdir(mode=0o700,parents=True)
    pg=Path(a.pg_bin);primary=root/'primary';restored=root/'restored';wal=root/'wal';wal.mkdir()
    secret=secrets.token_urlsafe(32);key=Fernet.generate_key();keyfile=root/'encryption.key';keyfile.write_bytes(key);keyfile.chmod(0o600);password=root/'password';password.write_text(secret);password.chmod(0o600)
    env=dict(os.environ,PGHOST='127.0.0.1',PGPORT=str(a.primary_port),PGUSER='drilladmin',PGPASSWORD=secret,DEBUG='1',MFA_REQUIRED='0',POSTGRES_HOST='127.0.0.1',POSTGRES_PORT=str(a.primary_port),POSTGRES_USER='drilladmin',POSTGRES_PASSWORD=secret,POSTGRES_DB='forvalta_drill',PRIVATE_MEDIA_ROOT=str(root/'media'),BACKUP_LOCAL_ROOT=str(root/'documents-repository'),BACKUP_ENCRYPTION_KEY=key.decode(),BACKUP_CONFIG_FILE=str(root/'configuration.env'))
    (root/'configuration.env').write_text('SYNTHETIC_CONFIGURATION=true\n');(root/'configuration.env').chmod(0o600)
    archive_script=root/'wal.py';archive_script.write_text('''import os,sys\nfrom pathlib import Path\nfrom cryptography.fernet import Fernet\nkey=Fernet(Path(sys.argv[2]).read_bytes());source=Path(sys.argv[3]);target=Path(sys.argv[4])\nif sys.argv[1]=='archive':\n data=source.read_bytes()\n if target.exists():\n  assert key.decrypt(target.read_bytes())==data\n else:\n  with open(target,'xb') as f:f.write(key.encrypt(data));f.flush();os.fsync(f.fileno())\nelse:\n with open(target,'wb') as f:f.write(key.decrypt(source.read_bytes()));f.flush();os.fsync(f.fileno())\n''')
    def cmd(args,stdin=None):
        r=subprocess.run([str(x) for x in args],input=stdin,text=True,env=env,capture_output=True,timeout=180)
        if r.returncode:raise RuntimeError('Command failed '+str(args[0])+' '+r.stderr[-1200:])
        return r.stdout.strip()
    def manage(*args,stdin=None):return cmd([sys.executable,ROOT/'backend/manage.py',*args],stdin)
    primary_up=False;restore_up=False;start=time.monotonic()
    result={'test':'isolated native PostgreSQL PITR, encrypted WAL/base backup and attachment bundle','status':'failed'}
    try:
        cmd([pg/'initdb','-D',primary,'-U','drilladmin','--pwfile',password,'--auth-host=scram-sha-256','--auth-local=trust'])
        archive=' '.join(map(shlex.quote,[sys.executable,str(archive_script),'archive',str(keyfile)]))+" '%p' "+shlex.quote(str(wal))+"/'%f'"
        with (primary/'postgresql.conf').open('a') as f:f.write(f"\nport={a.primary_port}\nlisten_addresses='127.0.0.1'\nunix_socket_directories=''\nwal_level=replica\narchive_mode=on\narchive_command='{archive.replace(chr(39),chr(39)*2)}'\n")
        cmd([pg/'pg_ctl','-D',primary,'-l',root/'primary.log','-w','start']);primary_up=True
        cmd([pg/'createdb','forvalta_drill']);manage('migrate','--noinput')
        fixture="from core.models import *;from core.storage import put_file;import hashlib;org=OrgUnit.objects.create(name='Synthetic church',kind='church');a=Asset.objects.create(org=org,name='BEFORE_BASE',kind='property');data=b'First private synthetic attachment';Document.objects.create(org=org,asset=a,title='First',file_key=put_file(data),sha256=hashlib.sha256(data).hexdigest(),size=len(data),mime='application/pdf')"
        manage('shell','-c',fixture)
        base=root/'base';cmd([pg/'pg_basebackup','-D',base,'-Fp','-X','stream','--checkpoint=fast'])
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w:gz') as tar:tar.add(base,arcname='.')
        (root/'base.enc').write_bytes(Fernet(key).encrypt(buffer.getvalue()));shutil.rmtree(base)
        manage('shell','-c',"from core.models import *;from core.storage import put_file;import hashlib;a=Asset.objects.first();data=b'Second attachment after base backup';Document.objects.create(org=a.org,asset=a,title='After base',file_key=put_file(data),sha256=hashlib.sha256(data).hexdigest(),size=len(data),mime='application/pdf')")
        name='forvalta_'+uuid.uuid4().hex
        with psycopg.connect(host='127.0.0.1',port=a.primary_port,user='drilladmin',password=secret,dbname='forvalta_drill',autocommit=True) as c:
            before=datetime.datetime.now(datetime.timezone.utc).isoformat();lsn=c.execute('SELECT pg_create_restore_point(%s)',(name,)).fetchone()[0];segment=c.execute('SELECT pg_walfile_name(%s)',(lsn,)).fetchone()[0];system=str(c.execute('SELECT system_identifier FROM pg_control_system()').fetchone()[0])
            meta={'name':name,'lsn':lsn,'wal':segment,'time':before,'system_identifier':system,'base_backup':'native-encrypted-test-base'}
            staged=json.loads(manage('recovery_bundle','stage',stdin=json.dumps(meta)))
            manage('shell','-c',"from core.models import *;Asset.objects.create(org=OrgUnit.objects.first(),name='AFTER_POINT_MUST_NOT_EXIST',kind='property')")
            c.execute('SELECT pg_switch_wal()')
            deadline=time.monotonic()+30
            while True:
                try:
                    Fernet(key).decrypt((wal/segment).read_bytes());break
                except (FileNotFoundError,InvalidToken):
                    if time.monotonic()>deadline:raise RuntimeError('WAL archive deadline exceeded')
                    time.sleep(.1)
        # Verify encrypted marker WAL before publishing the complete bundle.
        Fernet(key).decrypt((wal/segment).read_bytes());manage('recovery_bundle','commit','--id',staged['id'])
        restore_start=time.monotonic();restored.mkdir(mode=0o700)
        with tarfile.open(fileobj=io.BytesIO(Fernet(key).decrypt((root/'base.enc').read_bytes())),mode='r:gz') as tar:tar.extractall(restored,filter='data')
        restore_command=' '.join(map(shlex.quote,[sys.executable,str(archive_script),'restore',str(keyfile)]))+' '+shlex.quote(str(wal))+"/'%f' '%p'"
        with (restored/'postgresql.auto.conf').open('a') as f:f.write(f"\nport={a.restore_port}\narchive_mode=off\nrestore_command='{restore_command.replace(chr(39),chr(39)*2)}'\nrecovery_target_name='{name}'\nrecovery_target_action='promote'\n")
        (restored/'recovery.signal').touch();cmd([pg/'pg_ctl','-D',restored,'-l',root/'restore.log','-w','start']);restore_up=True
        env.update(POSTGRES_PORT=str(a.restore_port),PRIVATE_MEDIA_ROOT=str(root/'restored-media'))
        manage('recovery_bundle','restore','--id',staged['id'],'--target',str(root/'restored-media'),'--include-config')
        integrity=json.loads(manage('verify_integrity'))
        with psycopg.connect(host='127.0.0.1',port=a.restore_port,user='drilladmin',password=secret,dbname='forvalta_drill',autocommit=True) as c:
            names=[r[0] for r in c.execute('SELECT name FROM core_asset').fetchall()]
            if names!=['BEFORE_BASE']:raise RuntimeError('Restored past named checkpoint')
            if c.execute('SELECT pg_is_in_recovery()').fetchone()[0]:raise RuntimeError('Not promoted')
        if integrity['documents_verified']!=2:raise RuntimeError('Post-base attachment was not recovered')
        result.update(status='ok',integrity=integrity,post_checkpoint_record_absent=True,post_base_attachment_recovered=True,encrypted_base_and_wal=True,restore_seconds=round(time.monotonic()-restore_start,2),total_test_seconds=round(time.monotonic()-start,2),not_verified=['production Docker/pgBackRest/S3','production volume and RPO/RTO'])
    except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
    finally:
        if restore_up:cmd([pg/'pg_ctl','-D',restored,'-m','fast','-w','stop'])
        if primary_up:cmd([pg/'pg_ctl','-D',primary,'-m','fast','-w','stop'])
    Path(a.result).write_text(json.dumps(result,indent=2));print(json.dumps(result));return 0 if result['status']=='ok' else 1
if __name__=='__main__':sys.exit(main())
