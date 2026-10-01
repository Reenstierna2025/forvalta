from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
import hashlib,json,tempfile,zipfile
from django.contrib.auth import get_user_model
from django.core import serializers
from django.http import FileResponse
from django.db import transaction,connection
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from .models import OrgUnit,OrgRevision,Membership,Asset,WorkOrder,WorkComment,CostEntry,Schedule,Maintenance,BudgetScenario,RegistryEntry,Meter,Reading,Key,KeyLoan,Document,ReportTemplate,ReportSnapshot,Subscription,AuditEvent,Inspection,InspectionFinding
from .storage import read_file

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class FullExport(APIView):
    """Complete administrative portability export. Contains sensitive business data."""
    def get(self,request):
        if not request.user.is_superuser:raise PermissionDenied('Fullständig export kräver systemadministratör.')
        output=tempfile.SpooledTemporaryFile(max_size=8*1024*1024)
        manifest={'format':'forvalta-portable-1','generated_at':timezone.now().isoformat(),'files':{},'excludes':['passwords','MFA secrets','session cookies','public tracking tokens','notification queue','AI provider keys','AI request cache']}
        try:
            with transaction.atomic(),zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
                if connection.vendor=='postgresql':
                    with connection.cursor() as c:c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                def write(name,data):
                    archive.writestr(name,data);manifest['files'][name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
                models=[OrgUnit,OrgRevision,Membership,Asset,WorkOrder,WorkComment,CostEntry,Schedule,Maintenance,BudgetScenario,RegistryEntry,Meter,Reading,Key,KeyLoan,Document,ReportTemplate,ReportSnapshot,Subscription,AuditEvent,Inspection,InspectionFinding]
                for model in models:
                    fields=[f.name for f in model._meta.fields if f.name!='public_token_hash']
                    data=serializers.serialize('json',model.objects.order_by('pk').iterator(chunk_size=500),fields=fields).encode()
                    write('data/'+model._meta.model_name+'.json',data)
                users=list(get_user_model().objects.values('id','username','first_name','last_name','email','is_active'))
                write('data/users.json',json.dumps(users,ensure_ascii=False).encode())
                for d in Document.objects.iterator(chunk_size=100):write('attachments/'+str(d.id),read_file(d))
                archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            output.seek(0)
            response=FileResponse(output,as_attachment=True,filename='forvalta-data.zip',content_type='application/zip');response['Cache-Control']='no-store';return response
        except Exception:
            output.close();raise
