from core.health import health
from django.urls import path, include
from django.http import JsonResponse
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from core.inspections import InspectionViewSet,FindingViewSet
from core.api import *
from core.export import FullExport
from core.security import RecoverMFA,OwnSecurity,AccessUsers,ReduceAccess,ResetRequests,ApproveReset
from core.property_workspace import PropertyWorkspace
from core.ai import AISettings,AIContext,AIChat,AIApply
from core.auth import AuthView, MFAView, DemoLogin, UsersView
from core.reports import *

router=DefaultRouter()
for prefix,view in [('inspections',InspectionViewSet),('findings',FindingViewSet),('organizations',OrgViewSet),('assets',AssetViewSet),('work',WorkViewSet),('schedules',ScheduleViewSet),('maintenance',MaintenanceViewSet),('costs',CostViewSet),('registry',RegistryViewSet),('meters',MeterViewSet),('readings',ReadingViewSet),('keys',KeyViewSet),('loans',KeyLoanViewSet),('documents',DocumentViewSet),('scenarios',ScenarioViewSet),('templates',TemplateViewSet),('snapshots',SnapshotViewSet),('subscriptions',SubscriptionViewSet)]: router.register(prefix,view,basename=prefix)
urlpatterns=[path("api/v1/assets/<uuid:pk>/workspace/",PropertyWorkspace.as_view()),path("api/v1/ai/settings/",AISettings.as_view()),path("api/v1/ai/context/",AIContext.as_view()),path("api/v1/ai/chat/",AIChat.as_view()),path("api/v1/ai/apply/",AIApply.as_view()),path('api/v1/auth/recover/',RecoverMFA.as_view()),path('api/v1/security/',OwnSecurity.as_view()),path('api/v1/access/users/',AccessUsers.as_view()),path('api/v1/access/reduce/',ReduceAccess.as_view()),path('api/v1/access/resets/',ResetRequests.as_view()),path('api/v1/access/resets/<uuid:pk>/approve/',ApproveReset.as_view()),path('api/v1/full-export/',FullExport.as_view()),path('api/v1/',include(router.urls)),path('api/v1/auth/',AuthView.as_view()),path('api/v1/auth/mfa/',MFAView.as_view()),path('api/v1/auth/demo/',DemoLogin.as_view()),path('api/v1/users/',UsersView.as_view()),path('api/v1/bootstrap/',BootstrapView.as_view()),path('api/v1/reports/',ReportsView.as_view()),path('api/v1/audit/',AuditView.as_view()),path('api/v1/receipts/<uuid:key>/',ReceiptView.as_view()),path('api/v1/public/assets/',PublicAssets.as_view()),path('api/v1/public/issues/',PublicIssue.as_view()),path('api/v1/public/track/',PublicTrack.as_view()),path('api/schema/',SpectacularAPIView.as_view()),path('api/docs/',SpectacularSwaggerView.as_view(url_name='schema')),path('api/health/',health)]
urlpatterns.append(path('api/schema.json',SpectacularAPIView.as_view(),name='schema'))
