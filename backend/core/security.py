"""Session generations, one-use MFA recovery, and audited access reduction."""
import hashlib,hmac,secrets,time
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model,login
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied,ValidationError,NotFound
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from .models import AccountSecurity,RecoveryCode,MFAResetRequest,Membership,MFAProfile,AuditEvent
from .access import scope,expand,require
from .services import audit,mutation,check_version,Conflict


def state_for(user):return AccountSecurity.objects.get_or_create(user=user)[0]

def assert_current_session(request):
    # Authentication through the supported web API always has a Django session.
    if request.session.get('_auth_user_id'):
        state=state_for(request.user)
        active=get_user_model().objects.filter(pk=request.user.pk,is_active=True).exists()
        if not active or state.recovery_required or request.session.get('security_version')!=state.version:
            raise PermissionDenied('Sessionen har återkallats. Logga in på nytt.')

def revoke_sessions(user,recovery_required=None):
    state=state_for(user);state.version+=1
    if recovery_required is not None:state.recovery_required=recovery_required
    state.save();return state

def authenticated(request,user):
    state=state_for(user)
    login(request,user,backend='django.contrib.auth.backends.ModelBackend')
    request.session['security_version']=state.version
    request.session['preauth']=None

def preauthenticate(request,user):
    state=state_for(user);request.session.flush()
    request.session.update({'preauth':user.id,'preauth_at':time.time(),'preauth_version':state.version})

def candidate(request):
    if not request.session.get('preauth') or time.time()-request.session.get('preauth_at',0)>300:
        raise PermissionDenied('Logga in på nytt.')
    user=get_user_model().objects.filter(pk=request.session['preauth'],is_active=True).first()
    if not user or request.session.get('preauth_version')!=state_for(user).version:
        raise PermissionDenied('Inloggningen har återkallats. Börja om.')
    return user

def code_digest(user,code):
    normalized=str(code).strip().upper().replace('-','').replace(' ','')
    return hmac.new(settings.SECRET_KEY.encode(),f'recovery:{user.pk}:{normalized}'.encode(),hashlib.sha256).hexdigest()

def issue_codes(user):
    RecoveryCode.objects.filter(user=user,used_at__isnull=True).update(used_at=timezone.now())
    codes=['-'.join([token[i:i+8] for i in range(0,32,8)]) for token in [secrets.token_hex(16).upper() for _ in range(10)]]
    RecoveryCode.objects.bulk_create([RecoveryCode(user=user,digest=code_digest(user,c)) for c in codes])
    return codes

def reauthenticate(request):
    from .auth import cipher
    import pyotp
    user=get_user_model().objects.get(pk=request.user.pk)
    if not user.check_password(str(request.data.get('password',''))):raise PermissionDenied('Kontrollera lösenord och säkerhetskod.')
    if settings.MFA_REQUIRED:
        p=MFAProfile.objects.select_for_update().filter(user=user,enabled=True).first()
        if not p:raise PermissionDenied('Registrera flerfaktorsinloggning först.')
        totp=pyotp.TOTP(cipher().decrypt(p.encrypted_secret.encode()).decode());now=int(time.time())//30
        matched=next((c for c in [now,now-1,now+1] if hmac.compare_digest(totp.at(c*30),str(request.data.get('code','')))),None)
        if matched is None or matched<=p.last_counter:raise PermissionDenied('Kontrollera lösenord och en ny säkerhetskod.')
        p.last_counter=matched;p.save(update_fields=['last_counter'])

def lock_accounts(actor,target):
    # Include all system admins in one stable order to protect the last active admin.
    from django.db.models import Q
    list(get_user_model().objects.select_for_update().filter(Q(pk__in=[actor.pk,target.pk])|Q(is_superuser=True)).order_by('pk'))

def target_id(value):
    try:
        result=int(value)
        if result<1:raise ValueError()
        return result
    except (ValueError,TypeError):raise ValidationError('Ogiltig användare eller tilldelning.')

def reason(request):
    value=str(request.data.get('reason','')).strip()
    if not 10<=len(value)<=500:raise ValidationError('Ange en orsak på 10–500 tecken, utan hemligheter.')
    return value

class SensitiveView(APIView):
    def initial(self,request,*args,**kwargs):
        super().initial(request,*args,**kwargs)
        if request.method not in ['GET','HEAD','OPTIONS']:
            from .auth import rate_limit
            rate_limit(request,'security-stepup',10)

@method_decorator(csrf_protect,name='dispatch')
@extend_schema(request=OpenApiTypes.OBJECT,responses=OpenApiTypes.OBJECT)
class RecoverMFA(APIView):
    permission_classes=[AllowAny]
    def post(self,request):
        from .auth import rate_limit
        rate_limit(request,'mfa-recovery',5,900)
        user=candidate(request)
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=user.pk)
            user=candidate(request)
            digest=code_digest(user,request.data.get('recovery_code',''))
            code=RecoveryCode.objects.select_for_update().filter(user=user,digest=digest,used_at__isnull=True).first()
            reset=MFAResetRequest.objects.select_for_update().filter(user=user,token_digest=digest,state='approved',expires_at__gt=timezone.now(),account_version=state_for(user).version).first()
            if not code and not reset:raise ValidationError('Återställningskoden är ogiltig eller redan använd.')
            if code:code.used_at=timezone.now();code.save(update_fields=['used_at'])
            if reset:reset.state='used';reset.used_at=timezone.now();reset.version+=1;reset.save()
            state=revoke_sessions(user,True)
            AuditEvent.objects.create(actor=user,entity='accountsecurity',entity_id=str(user.pk),action='mfa_recovery_started')
            preauthenticate(request,user);request.session['recovery_authorized']=True
        return Response({'enroll':True,'csrf':get_token(request)})

@extend_schema(request=OpenApiTypes.OBJECT,responses=OpenApiTypes.OBJECT)
class OwnSecurity(SensitiveView):
    def get(self,request):
        return Response({'mfa_enabled':MFAProfile.objects.filter(user=request.user,enabled=True).exists(),'recovery_codes_remaining':RecoveryCode.objects.filter(user=request.user,used_at__isnull=True).count(),'version':state_for(request.user).version})
    @transaction.atomic
    def post(self,request):
        get_user_model().objects.select_for_update().get(pk=request.user.pk);assert_current_session(request);reauthenticate(request)
        action=request.data.get('action')
        if action=='revoke_sessions':
            revoke_sessions(request.user);authenticated(request,request.user)
            AuditEvent.objects.create(actor=request.user,entity='accountsecurity',entity_id=str(request.user.pk),action='other_sessions_revoked')
            return Response({'ok':True,'csrf':get_token(request)})
        if action=='recovery_codes':
            if not MFAProfile.objects.filter(user=request.user,enabled=True).exists():raise ValidationError('Flerfaktorsinloggning är inte registrerad.')
            codes=issue_codes(request.user)
            AuditEvent.objects.create(actor=request.user,entity='accountsecurity',entity_id=str(request.user.pk),action='recovery_codes_rotated')
            return Response({'recovery_codes':codes})
        raise ValidationError('Okänd åtgärd.')

@extend_schema(request=OpenApiTypes.OBJECT,responses=OpenApiTypes.OBJECT)
class AccessUsers(APIView):
    def get(self,request):
        ids=scope(request.user,['admin'])
        grants=Membership.objects.filter(org_id__in=ids).select_related('org')
        users=get_user_model().objects.all() if request.user.is_superuser else get_user_model().objects.filter(pk__in=grants.values('user_id'))
        return Response([{'id':u.pk,'name':u.get_full_name() or u.username,'username':u.username,'is_active':u.is_active,'is_superuser':u.is_superuser,'version':state_for(u).version,'grants':[{'id':g.pk,'org':str(g.org_id),'org_name':g.org.name,'role':g.role,'active':g.active,'version':g.version,'descendants':g.descendants,'finance':g.finance} for g in grants if g.user_id==u.pk]} for u in users.order_by('username')])

@extend_schema(request=OpenApiTypes.OBJECT,responses=OpenApiTypes.OBJECT)
class ReduceAccess(SensitiveView):
    @transaction.atomic
    def post(self,request):
        target=get_user_model().objects.filter(pk=target_id(request.data.get('user'))).first()
        if not target:raise NotFound()
        if target.pk==request.user.pk:raise ValidationError('Använd Mina säkerhetsinställningar för egna sessioner. Egen åtkomst kan inte stängas här.')
        lock_accounts(request.user,target)
        def change():
            why=reason(request);action=request.data.get('action')
            if action=='revoke_grant':
                grant=Membership.objects.select_for_update().filter(pk=target_id(request.data.get('grant')),user=target).first()
                if not grant:raise NotFound()
                require(request.user,grant.org_id,['admin'])
                if grant.descendants and not expand(grant.org_id).issubset(scope(request.user,['admin'])):raise PermissionDenied()
                if target.is_superuser:raise ValidationError('Systemadministratörens åtkomst styrs av kontot, inte denna tilldelning.')
                check_version(request,grant);reauthenticate(request)
                grant.active=False;grant.version+=1;grant.save();audit(request.user,grant,'access_revoked',{'reason':why})
                revoke_sessions(target)
                return {'id':grant.pk,'version':grant.version},200
            if action not in ['disable_account','revoke_sessions'] or not request.user.is_superuser:raise PermissionDenied()
            state=state_for(target);check_version(request,state);reauthenticate(request)
            if action=='disable_account':
                if target.is_superuser and get_user_model().objects.filter(is_superuser=True,is_active=True).count()<=1:raise ValidationError('Den sista aktiva systemadministratören får inte stängas.')
                target.is_active=False;target.save(update_fields=['is_active'])
            state=revoke_sessions(target)
            AuditEvent.objects.create(actor=request.user,entity='accountsecurity',entity_id=str(target.pk),action=action,after={'version':state.version,'reason':why})
            return {'id':target.pk,'version':state.version},200
        result,status=mutation(request,change);return Response(result,status=status)

@extend_schema(request=OpenApiTypes.OBJECT,responses=OpenApiTypes.OBJECT)
class ResetRequests(SensitiveView):
    def get(self,request):
        if not request.user.is_superuser:raise PermissionDenied()
        return Response(list(MFAResetRequest.objects.order_by('-created_at').values('id','user_id','user__username','requested_by_id','approved_by_id','state','version','reason','expires_at')[:100]))
    @transaction.atomic
    def post(self,request):
        if not request.user.is_superuser:raise PermissionDenied()
        target=get_user_model().objects.filter(pk=target_id(request.data.get('user')),is_active=True).first()
        if not target or target.pk==request.user.pk:raise ValidationError('Välj en annan aktiv användare.')
        lock_accounts(request.user,target)
        def create():
            reauthenticate(request);why=reason(request)
            reset=MFAResetRequest.objects.create(user=target,requested_by=request.user,reason=why,account_version=state_for(target).version,expires_at=timezone.now()+timedelta(minutes=30))
            audit(request.user,reset,'mfa_reset_requested')
            return {'id':reset.pk,'version':reset.version},201
        data,status=mutation(request,create);return Response(data,status=status)

@extend_schema(request=OpenApiTypes.OBJECT,responses=OpenApiTypes.OBJECT)
class ApproveReset(SensitiveView):
    @transaction.atomic
    def post(self,request,pk):
        if not request.user.is_superuser:raise PermissionDenied()
        reset=MFAResetRequest.objects.filter(pk=pk).select_related('user').first()
        if not reset:raise NotFound()
        lock_accounts(request.user,reset.user);assert_current_session(request)
        reset=MFAResetRequest.objects.select_for_update().get(pk=pk)
        check_version(request,reset)
        if request.user.pk in [reset.requested_by_id,reset.user_id]:raise PermissionDenied('En annan systemadministratör måste godkänna återställningen.')
        if reset.state!='pending' or reset.expires_at<=timezone.now() or not reset.user.is_active:raise Conflict('Begäran är avslutad eller har gått ut.')
        if state_for(reset.user).version!=reset.account_version:raise Conflict('Kontots säkerhet har ändrats. Skapa en ny begäran.')
        reauthenticate(request)
        token=secrets.token_hex(16).upper();state=revoke_sessions(reset.user,True)
        RecoveryCode.objects.filter(user=reset.user,used_at__isnull=True).update(used_at=timezone.now())
        reset.token_digest=code_digest(reset.user,token);reset.approved_by=request.user;reset.state='approved';reset.version+=1;reset.account_version=state.version;reset.expires_at=timezone.now()+timedelta(hours=1);reset.save()
        audit(request.user,reset,'mfa_reset_approved')
        # Never place this bearer secret in an idempotency receipt or the audit log.
        return Response({'id':reset.pk,'version':reset.version,'recovery_code':token,'expires_at':reset.expires_at})
