import hashlib, io, os, shlex, subprocess, tempfile, uuid
from pathlib import Path
import boto3
from PIL import Image
from django.conf import settings
from rest_framework.exceptions import ValidationError

MAX_FILE=20*1024*1024

def s3(): return boto3.client('s3',endpoint_url=settings.S3_ENDPOINT_URL,region_name=settings.S3_REGION)

def inspect_upload(file):
    if not file or file.size>MAX_FILE or file.size==0: raise ValidationError('Välj en fil på högst 20 MB.')
    data=file.read()
    ext=Path(file.name).suffix.lower()
    if ext in ['.jpg','.jpeg','.png']:
        try:
            im=Image.open(io.BytesIO(data)); im.verify()
            if im.format not in ['PNG','JPEG']: raise ValueError()
        except Exception: raise ValidationError('Bilden är skadad eller har fel format.')
        mime='image/png' if im.format=='PNG' else 'image/jpeg'
    elif ext=='.pdf' and data.startswith(b'%PDF-'): mime='application/pdf'
    else: raise ValidationError('Tillåtna format är PDF, PNG och JPEG.')
    if settings.FILE_SCAN_COMMAND:
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(data); tmp.flush()
            try: result=subprocess.run(shlex.split(settings.FILE_SCAN_COMMAND)+[tmp.name],capture_output=True,timeout=60)
            except Exception: raise ValidationError('Filkontrollen är inte tillgänglig. Försök senare.')
            if result.returncode!=0: raise ValidationError('Filen godkändes inte av filkontrollen.')
    elif not settings.DEBUG: raise ValidationError('Filkontroll måste vara aktiverad innan filer kan sparas.')
    return data,mime,hashlib.sha256(data).hexdigest()

def put_file(data):
    key='documents/'+str(uuid.uuid4())
    if settings.S3_BUCKET:
        s3().put_object(Bucket=settings.S3_BUCKET,Key=key,Body=data,ContentType='application/octet-stream',ServerSideEncryption='AES256')
    elif settings.DEBUG:
        path=settings.MEDIA_ROOT/key; path.parent.mkdir(parents=True,exist_ok=True)
        with open(path,'xb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
    else: raise ValidationError('Privat dokumentlagring är inte konfigurerad.')
    return key

def read_file(doc):
    if settings.S3_BUCKET: data=s3().get_object(Bucket=settings.S3_BUCKET,Key=doc.file_key)['Body'].read()
    else: data=(settings.MEDIA_ROOT/doc.file_key).read_bytes()
    if hashlib.sha256(data).hexdigest()!=doc.sha256: raise ValidationError('Filens integritetskontroll misslyckades.')
    return data
