import ipaddress
from django.conf import settings
class TrustedProxyAddress:
    """Enabled only when the API is reachable exclusively through our reverse proxy."""
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        if settings.TRUST_PROXY:
            try:request.META['REMOTE_ADDR']=str(ipaddress.ip_address(request.META.get('HTTP_X_REAL_IP','')))
            except ValueError:pass
        response=self.get_response(request)
        if request.path.startswith('/api/'):
            response['Cache-Control']='private, no-store'
            response['Referrer-Policy']='no-referrer'
        return response

class SessionGeneration:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        from django.contrib.auth import logout
        invalid=bool(request.session.get('_auth_user_id')) and not request.user.is_authenticated
        if request.user.is_authenticated:
            from .security import state_for
            state=state_for(request.user)
            invalid=state.recovery_required or request.session.get('security_version')!=state.version
        if invalid:
            logout(request)
            if request.path.startswith('/api/v1/') and not request.path.startswith(('/api/v1/auth/','/api/v1/public/')):
                from django.http import JsonResponse
                return JsonResponse({'code':'session_revoked','detail':'Din session har återkallats. Logga in på nytt.'},status=401)
        return self.get_response(request)
