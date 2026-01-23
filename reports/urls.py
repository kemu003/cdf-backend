# reports/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router
router = DefaultRouter()
router.register(r'', views.ReportViewSet, basename='report')  # Empty string for root
router.register(r'templates', views.ReportTemplateViewSet, basename='reporttemplate')
router.register(r'schedules', views.ReportScheduleViewSet, basename='reportschedule')
router.register(r'logs', views.ReportLogViewSet, basename='reportlog')

# Define URL patterns
urlpatterns = [
    # Router URLs
    path('', include(router.urls)),
    
    # Function-based views for backward compatibility
    path('report-types/', views.report_types_view, name='report_types'),
    path('report-filters/', views.report_filters_view, name='report_filters'),
    path('quick-report/', views.generate_quick_report_view, name='generate_quick_report'),
    path('bulk-delete/', views.bulk_delete_reports_view, name='bulk_delete_reports'),
]