from django.db.models import Q
from rest_framework.exceptions import PermissionDenied
from .models import OrgUnit, Membership, WorkOrder


def expand(org_id):
    result = {org_id}
    frontier = {org_id}
    while frontier:
        frontier = set(OrgUnit.objects.filter(parent_id__in=frontier).values_list('id',flat=True))-result
        result |= frontier
    return result


def scope(user, roles=None, finance=False):
    if not user.is_authenticated or not user.is_active: return set()
    if user.is_superuser: return set(OrgUnit.objects.values_list('id',flat=True))
    grants = Membership.objects.filter(user=user,active=True)
    if roles: grants = grants.filter(role__in=roles)
    if finance: grants = grants.filter(finance=True).exclude(role='contractor')
    result = set()
    for g in grants:
        result |= expand(g.org_id) if g.descendants else {g.org_id}
    return result

INTERNAL = ['admin','manager','worker','reader']
EDIT = ['admin','manager','worker']
MANAGE = ['admin','manager']


def require(user, org_id, roles=EDIT, finance=False):
    if org_id not in scope(user,roles,finance): raise PermissionDenied('Du saknar behörighet för den här åtgärden.')


def work_scope(user):
    return WorkOrder.objects.filter(Q(org_id__in=scope(user,INTERNAL)) | Q(org_id__in=scope(user,['contractor']),assigned_to=user))


def can_work(user, work):
    if work.org_id in scope(user,EDIT): return True
    return work.org_id in scope(user,['contractor']) and work.assigned_to_id==user.id
