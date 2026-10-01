import os,json,tempfile,uuid
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet,InvalidToken
from django.test import TestCase,override_settings
from .models import OrgUnit,Asset,Document
from .backup import Repository,stage,commit,completed,verify,restore_local,BackupError,digest

@override_settings(DEBUG=True,S3_BUCKET=None)
class BackupTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'BACKUP_LOCAL_ROOT':str(self.root/'repository'),'BACKUP_ENCRYPTION_KEY':Fernet.generate_key().decode()});self.env.start();self.addCleanup(self.env.stop)
        self.settings=override_settings(MEDIA_ROOT=self.root/'media');self.settings.enable();self.addCleanup(self.settings.disable)
        org=OrgUnit.objects.create(name='Kyrkan',kind='church');asset=Asset.objects.create(org=org,name='Prov',kind='property');self.data=b'Private synthetic attachment'
        self.file_key='documents/'+str(uuid.uuid4());path=self.root/'media'/self.file_key;path.parent.mkdir(parents=True);path.write_bytes(self.data)
        self.doc=Document.objects.create(org=org,asset=asset,title='Prov',file_key=self.file_key,size=len(self.data),sha256=digest(self.data),mime='application/pdf')
        self.checkpoint={'name':'forvalta_'+uuid.uuid4().hex,'lsn':'0/1234AB','wal':'000000010000000000000001','time':'2026-10-01T10:00:00+00:00','system_identifier':'12345','base_backup':'synthetic-base'}
        self.repo=Repository()
    def test_bundle_not_complete_until_commit_and_restores_hashes(self):
        m=stage(self.repo,self.checkpoint,b'SECRET_KEY=synthetic')
        with self.assertRaises(BackupError):completed(self.repo)
        commit(self.repo,m['id']);restored=completed(self.repo,m['id']);self.assertEqual(verify(self.repo,restored),1)
        target=self.root/'restored';restore_local(self.repo,restored,target,True)
        self.assertEqual((target/self.file_key).read_bytes(),self.data)
        self.assertEqual((target/'configuration.env').stat().st_mode&0o777,0o600)
        encrypted=(self.root/'repository'/m['documents'][0]['blob']).read_bytes();self.assertNotIn(self.data,encrypted)
    def test_corrupt_or_missing_attachment_cannot_publish_complete(self):
        m=stage(self.repo,self.checkpoint,b'config');(self.root/'repository'/m['documents'][0]['blob']).write_bytes(b'corrupt')
        with self.assertRaises(InvalidToken):commit(self.repo,m['id'])
        with self.assertRaises(BackupError):completed(self.repo)
    def test_source_checksum_and_no_overwrite(self):
        (self.root/'media'/self.file_key).write_bytes(b'corrupt')
        with self.assertRaises(Exception):stage(self.repo,self.checkpoint,b'config')
        self.repo.put('config/test.enc',b'one')
        with self.assertRaises(BackupError):self.repo.put('config/test.enc',b'two')
    def test_restore_rejects_nonempty_destination_and_traversal(self):
        m=stage(self.repo,self.checkpoint,b'config');target=self.root/'occupied';target.mkdir();(target/'keep').write_text('keep')
        with self.assertRaises(BackupError):restore_local(self.repo,m,target)
        m['documents'][0]['file_key']='../../escape'
        with self.assertRaises(BackupError):restore_local(self.repo,m,self.root/'safe')
    def test_wrong_encryption_key_and_incomplete_metadata(self):
        with self.assertRaises(BackupError):stage(self.repo,{'name':'bad'},b'config')
        m=stage(self.repo,self.checkpoint,b'config');commit(self.repo,m['id'])
        with patch.dict(os.environ,{'BACKUP_ENCRYPTION_KEY':Fernet.generate_key().decode()}):
            with self.assertRaises(InvalidToken):completed(Repository())
