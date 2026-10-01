"""Encrypted immutable attachment bundles tied to an explicit PostgreSQL checkpoint.
Only the isolated operations container receives these credentials.
"""
import hashlib,json,os,re,uuid
from pathlib import Path
from datetime import datetime,timezone
import boto3
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet
from django.conf import settings
from .models import Document
from .storage import read_file

class BackupError(Exception):pass

def digest(data):return hashlib.sha256(data).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def valid_id(value):return str(uuid.UUID(str(value)))
def document_path(value):
    if not re.fullmatch(r'documents/[0-9a-f-]{36}',value):raise BackupError('Unsafe document path')
    valid_id(value.split('/')[1]);return value

class Repository:
    def __init__(self):
        self.cipher=Fernet(os.environ['BACKUP_ENCRYPTION_KEY'].encode())
        self.local=os.getenv('BACKUP_LOCAL_ROOT')
        if self.local:
            if not settings.DEBUG:raise BackupError('Local backup repository is only permitted in development')
            self.root=Path(self.local).resolve();self.root.mkdir(parents=True,exist_ok=True)
        else:
            endpoint=os.environ['BACKUP_S3_ENDPOINT'];self.bucket=os.environ['BACKUP_S3_BUCKET']
            if not endpoint.startswith('https://'):raise BackupError('Backup endpoint requires HTTPS')
            if self.bucket==settings.S3_BUCKET and endpoint==settings.S3_ENDPOINT_URL:raise BackupError('Backup must use a separate bucket')
            self.client=boto3.client('s3',endpoint_url=endpoint,region_name=os.getenv('BACKUP_S3_REGION','eu-north-1'),aws_access_key_id=os.environ['BACKUP_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['BACKUP_SECRET_ACCESS_KEY'])
    def keys(self,prefix):
        if self.local:return sorted(str(p.relative_to(self.root)) for p in self.root.glob(prefix+'*') if p.is_file())
        result=[]
        for page in self.client.get_paginator('list_objects_v2').paginate(Bucket=self.bucket,Prefix=prefix):result += [r['Key'] for r in page.get('Contents',[])]
        return sorted(result)
    def read(self,key):
        if not re.fullmatch(r'(blobs|staged|complete|config)/[a-zA-Z0-9_.-]+',key):raise BackupError('Unsafe repository key')
        if self.local:encrypted=(self.root/key).read_bytes()
        else:encrypted=self.client.get_object(Bucket=self.bucket,Key=key)['Body'].read()
        return self.cipher.decrypt(encrypted)
    def put(self,key,data):
        # Content-addressed/UUID keys; never replace a previous backup object.
        try:
            existing=self.read(key)
            if existing!=data:raise BackupError('Refusing to replace different backup data')
            return
        except FileNotFoundError:pass
        except ClientError as e:
            if e.response['Error']['Code'] not in ['NoSuchKey','404']:raise
        encrypted=self.cipher.encrypt(data)
        if self.local:
            p=self.root/key;p.parent.mkdir(parents=True,exist_ok=True)
            # A temp file + exclusive hard link publishes only after fsync, without overwriting.
            temp=p.parent/(str(uuid.uuid4())+'.tmp')
            try:
                with open(temp,'xb') as f:f.write(encrypted);f.flush();os.fsync(f.fileno())
                os.link(temp,p)
                fd=os.open(p.parent,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
            finally:temp.unlink(missing_ok=True)
        else:self.client.put_object(Bucket=self.bucket,Key=key,Body=encrypted,ServerSideEncryption='AES256',IfNoneMatch='*',ContentType='application/octet-stream')
        if self.read(key)!=data:raise BackupError('Backup readback failed')

def stage(repo,checkpoint,config):
    required=['name','lsn','wal','time','system_identifier','base_backup']
    if any(not checkpoint.get(k) for k in required):raise BackupError('Incomplete PostgreSQL checkpoint')
    if not re.fullmatch(r'forvalta_[a-f0-9]{32}',checkpoint['name']):raise BackupError('Invalid checkpoint name')
    if not re.fullmatch(r'[0-9A-F]{24}',checkpoint['wal']):raise BackupError('Invalid WAL name')
    if not re.fullmatch(r'[0-9A-F]+/[0-9A-F]+',checkpoint['lsn']):raise BackupError('Invalid LSN')
    id=str(uuid.uuid4());items=[]
    # Checkpoint was created BEFORE this query. Immutable documents guarantee
    # that all documents visible at that checkpoint are included (possibly extras).
    for d in Document.objects.order_by('id').iterator(chunk_size=500):
        document_path(d.file_key);data=read_file(d)
        if len(data)!=d.size:raise BackupError('Attachment size mismatch')
        blob='blobs/'+d.sha256+'.enc';repo.put(blob,data)
        items.append({'id':str(d.id),'file_key':d.file_key,'sha256':d.sha256,'size':d.size,'blob':blob})
    config_key='config/'+digest(config)+'.enc';repo.put(config_key,config)
    manifest={'format':'forvalta-recovery-1','id':id,'checkpoint':checkpoint,'documents':items,'config_key':config_key,'config_sha256':digest(config),'staged_at':datetime.now(timezone.utc).isoformat()}
    repo.put('staged/'+id+'.json.enc',encode(manifest));return manifest

def verify(repo,manifest):
    if manifest.get('format')!='forvalta-recovery-1':raise BackupError('Unsupported backup format')
    for d in manifest['documents']:
        document_path(d['file_key']);data=repo.read(d['blob'])
        if len(data)!=d['size'] or digest(data)!=d['sha256']:raise BackupError('Attachment checksum mismatch')
    if digest(repo.read(manifest['config_key']))!=manifest['config_sha256']:raise BackupError('Configuration checksum mismatch')
    return len(manifest['documents'])

def commit(repo,id):
    # Called ONLY by the host coordinator after pgBackRest archive-get succeeds.
    manifest=json.loads(repo.read('staged/'+valid_id(id)+'.json.enc'));verify(repo,manifest)
    repo.put('complete/'+datetime.fromisoformat(manifest['checkpoint']['time']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'_'+id+'.json.enc',encode(manifest));return manifest

def completed(repo,id=None):
    keys=[k for k in repo.keys('complete/') if k.endswith('.json.enc')]
    if id:keys=[k for k in keys if k.endswith('_'+valid_id(id)+'.json.enc')]
    if not keys:raise BackupError('No completed backup')
    return json.loads(repo.read(keys[-1]))

def restore_local(repo,manifest,target,include_config=False):
    target=Path(target).resolve()
    if target.exists() and any(target.iterdir()):raise BackupError('Restore destination must be empty')
    verify(repo,manifest);target.mkdir(mode=0o700,parents=True,exist_ok=True)
    for d in manifest['documents']:
        path=target/document_path(d['file_key']);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        data=repo.read(d['blob'])
        if len(data)!=d['size'] or digest(data)!=d['sha256']:raise BackupError('Restore checksum mismatch')
        with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    if include_config:
        fd=os.open(target/'configuration.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(repo.read(manifest['config_key']));f.flush();os.fsync(f.fileno())
    return {'documents':len(manifest['documents']),'checkpoint':manifest['checkpoint']}

def restore_s3(repo,manifest):
    endpoint=os.environ['RESTORE_S3_ENDPOINT'];bucket=os.environ['RESTORE_S3_BUCKET']
    if not endpoint.startswith('https://'):raise BackupError('Restore endpoint requires HTTPS')
    if (endpoint,bucket) in [(settings.S3_ENDPOINT_URL,settings.S3_BUCKET),(os.getenv('BACKUP_S3_ENDPOINT'),os.getenv('BACKUP_S3_BUCKET'))]:raise BackupError('Restore cannot target primary or backup storage')
    client=boto3.client('s3',endpoint_url=endpoint,region_name=os.getenv('RESTORE_S3_REGION','eu-north-1'),aws_access_key_id=os.environ['RESTORE_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['RESTORE_SECRET_ACCESS_KEY'])
    if client.list_objects_v2(Bucket=bucket,MaxKeys=1).get('Contents'):raise BackupError('Restore bucket must be empty')
    verify(repo,manifest)
    for d in manifest['documents']:
        data=repo.read(d['blob'])
        if len(data)!=d['size'] or digest(data)!=d['sha256']:raise BackupError('Restore checksum mismatch')
        client.put_object(Bucket=bucket,Key=document_path(d['file_key']),Body=data,ServerSideEncryption='AES256',IfNoneMatch='*',ContentType='application/octet-stream')
        actual=client.get_object(Bucket=bucket,Key=d['file_key'])['Body'].read()
        if len(actual)!=d['size'] or digest(actual)!=d['sha256']:raise BackupError('Restored object readback failed')
    return {'documents':len(manifest['documents']),'bucket':bucket,'checkpoint':manifest['checkpoint']}
