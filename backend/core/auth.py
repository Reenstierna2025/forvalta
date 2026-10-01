from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
import base64, hashlib, hmac, time
import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import ValidationError, PermissionDenied, Throttled
from .models import MFAProfile, RateBucket, Membership, OrgUnit
from .access import scope, require, expand
from .services import audit
from .security import authenticated,preauthenticate,candidate,state_for,revoke_sessions,issue_codes


def rate_limit(request, area, limit=15, window=900):
    source=request.META.get('REMOTE_ADDR','unknown')
    digest=hmac.new(settings.SECRET_KEY.encode(),source.encode(),hashlib.sha256).hexdigest()
    key=area+':'+digest
    with transaction.atomic():
        RateBucket.objects.get_or_create(key=key,defaults={'started_at':timezone.now()})
        b=RateBucket.objects.select_for_update().get(pk=key)
        if (timezone.now()-b.started_at).total_seconds()>=window:
            b.started_at=timezone.now(); b.count=0
        b.count+=1; b.save()
        blocked=b.count>limit
    if blocked: raise Throttled(detail='För många försök. Vänta en stund och försök igen.')


def cipher():
    key=settings.MFA_ENCRYPTION_KEY
    if not key and settings.DEBUG: key=base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def user_data(user):
    return {'id':user.id,'name':user.get_full_name() or user.username,'username':user.username,'superuser':user.is_superuser,'grants':list(Membership.objects.filter(user=user,active=True).values('org_id','role','descendants','finance'))}

@method_decorator(csrf_protect,name='dispatch')
@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class AuthView(APIView):
    permission_classes=[AllowAny]
    def get(self,request):
        token=get_token(request)
        return Response({'user':user_data(request._request.user) if request._request.user.is_authenticated else None,'csrf':token,'demo':settings.DEMO_MODE,'pilot':settings.PILOT_MODE,'mfa_required':settings.MFA_REQUIRED,'source_url':settings.SOURCE_URL})
    def post(self,request):
        rate_limit(request,'login')
        user=authenticate(request,username=request.data.get('username',''),password=request.data.get('password',''))
        if not user: raise ValidationError({'detail':'Användarnamn eller lösenord stämmer inte.'})
        if settings.MFA_REQUIRED:
            preauthenticate(request,user)
            return Response({'mfa':True,'enroll':not MFAProfile.objects.filter(user=user,enabled=True).exists()})
        authenticated(request,user)
        return Response({'user':user_data(user),'csrf':get_token(request)})
    def delete(self,request):
        logout(request); return Response({'ok':True})

@method_decorator(csrf_protect,name='dispatch')
@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class MFAView(APIView):
    permission_classes=[AllowAny]
    def candidate(self,request):return candidate(request)
    def get(self,request):
        user=candidate(request);recovering=request.session.get('recovery_authorized',False)
        if state_for(user).recovery_required and not recovering:return Response({'enroll':False,'recovery_required':True})
        if MFAProfile.objects.filter(user=user,enabled=True).exists() and not recovering:return Response({'enroll':False})
        secret=request.session.get('mfa_pending') or pyotp.random_base32();request.session['mfa_pending']=secret
        return Response({'enroll':True,'secret':secret,'uri':pyotp.TOTP(secret).provisioning_uri(user.username,issuer_name='Förvalta')})
    def post(self,request):
        rate_limit(request,'mfa',10)
        user=candidate(request);codes=None
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=user.pk);user=candidate(request)
            recovering=request.session.get('recovery_authorized',False)
            if state_for(user).recovery_required and not recovering:raise PermissionDenied('Använd en återställningskod.')
            profile=MFAProfile.objects.select_for_update().filter(user=user).first()
            enrolling=not profile or not profile.enabled or recovering
            secret=request.session.get('mfa_pending','') if enrolling else cipher().decrypt(profile.encrypted_secret.encode()).decode()
            if not secret:raise ValidationError('Starta registreringen på nytt.')
            totp=pyotp.TOTP(secret);current=int(time.time())//30
            matched=next((c for c in [current,current-1,current+1] if hmac.compare_digest(totp.at(c*30),str(request.data.get('code','')))),None)
            if matched is None or (not enrolling and matched<=profile.last_counter):raise ValidationError({'code':'Koden är fel eller har redan använts.'})
            if not profile:profile=MFAProfile(user=user)
            profile.encrypted_secret=cipher().encrypt(secret.encode()).decode();profile.enabled=True;profile.last_counter=matched;profile.save()
            if enrolling:
                revoke_sessions(user,False);codes=issue_codes(user)
                from .models import AuditEvent
                AuditEvent.objects.create(actor=user,entity='accountsecurity',entity_id=str(user.pk),action='mfa_enrolled')
            request.session.flush();authenticated(request,user)
        result={'user':user_data(user),'csrf':get_token(request)}
        if codes:result['recovery_codes']=codes
        return Response(result)

@method_decorator(csrf_protect,name='dispatch')
@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class DemoLogin(APIView):
    permission_classes=[AllowAny]
    def post(self,request):
        if not settings.DEMO_MODE or request.META.get('REMOTE_ADDR') not in ['127.0.0.1','::1']: raise PermissionDenied()
        user=get_user_model().objects.get(username='demo')
        authenticated(request,user)
        return Response({'user':user_data(user),'csrf':get_token(request)})

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class UsersView(APIView):
    def get(self,request):
        ids=scope(request.user,['admin','manager','worker'])
        users=get_user_model().objects.filter(membership__org_id__in=ids,membership__active=True,is_active=True).distinct()
        return Response([{'id':u.id,'name':u.get_full_name() or u.username} for u in users])
    @transaction.atomic
    def post(self,request):
        from .services import mutation
        def create():
            try: org=OrgUnit.objects.get(pk=request.data.get('org'))
            except (OrgUnit.DoesNotExist,ValueError): raise ValidationError('Välj en organisationsenhet.')
            require(request.user,org.id,['admin'])
            if request.data.get('finance'): require(request.user,org.id,['admin'],finance=True)
            requested_scope=expand(org.id) if request.data.get('descendants',False) else {org.id}
            if not requested_scope.issubset(scope(request.user,['admin'])):raise PermissionDenied('Tilldelningen omfattar enheter du inte får administrera.')
            if request.data.get('finance') and not requested_scope.issubset(scope(request.user,['admin'],True)):raise PermissionDenied('Ekonomibehörigheten omfattar enheter du inte får administrera.')
            role=request.data.get('role','worker')
            if role=='contractor' and request.data.get('finance'):raise ValidationError('Entreprenörer får inte ekonomibehörighet.')
            if role not in dict(Membership._meta.get_field('role').choices): raise ValidationError('Ogiltig roll.')
            user=get_user_model()(username=request.data.get('username',''),email=request.data.get('email',''),first_name=request.data.get('name',''))
            password=request.data.get('password',''); validate_password(password,user)
            user.set_password(password); user.full_clean(); user.save()
            grant=Membership(user=user,org=org,role=role,descendants=request.data.get('descendants',False),finance=request.data.get('finance',False))
            grant.full_clean(); grant.save(); audit(request.user,grant,'access_granted')
            return {'id':user.id},201
        data,status=mutation(request,create); return Response(data,status=status)
