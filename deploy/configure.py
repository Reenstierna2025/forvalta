#!/usr/bin/env python3
"""Create a private local configuration without overwriting existing secrets."""
import base64,os,secrets
from pathlib import Path
root=Path(__file__).resolve().parents[1];target=root/'.env'
if target.exists():raise SystemExit('.env already exists; edit it without regenerating secrets.')
values={'BACKUP_ENCRYPTION_KEY':base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),'SECRET_KEY':secrets.token_urlsafe(64),'POSTGRES_PASSWORD':secrets.token_urlsafe(40),'DB_ADMIN_PASSWORD':secrets.token_urlsafe(40),'MFA_ENCRYPTION_KEY':base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),'PGBACKREST_REPO1_CIPHER_PASS':secrets.token_urlsafe(48)}
text=(root/'.env.example').read_text()
for key,value in values.items():text=text.replace(key+'=\n',key+'='+value+'\n')
fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as stream:stream.write(text)
print('Created private .env. Set domain, storage and mail settings before installation.')
