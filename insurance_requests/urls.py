"""
URL маршруты для приложения insurance_requests
"""
from django.urls import path
from . import views, media_views, monitoring_views

app_name = 'insurance_requests'

urlpatterns = [
    # Main application URLs
    path('', views.request_list, name='request_list'),
    path('upload/', views.upload_excel, name='upload_excel'),
    path('<int:pk>/', views.request_detail, name='request_detail'),
    path('<int:pk>/edit/', views.edit_request, name='edit_request'),
    path('<int:pk>/generate-email/', views.generate_email, name='generate_email'),
    path('<int:pk>/preview-email/', views.preview_email, name='preview_email'),
    path('<int:pk>/send-email/', views.send_email, name='send_email'),
    
    # Secure media file serving URLs
    path('attachment/<int:attachment_id>/', media_views.serve_attachment, name='serve_attachment'),
    path('attachment/<int:attachment_id>/info/', media_views.attachment_info, name='attachment_info'),
    path('attachment/<int:attachment_id>/download/', media_views.download_attachment, name='download_attachment'),
    
    # Monitoring URLs
    path('monitoring/', monitoring_views.monitoring_dashboard, name='monitoring_dashboard'),
    path('monitoring/api/summary/', monitoring_views.monitoring_api_summary, name='monitoring_api_summary'),
    path('monitoring/api/performance/', monitoring_views.monitoring_api_performance, name='monitoring_api_performance'),
    path('monitoring/api/security/', monitoring_views.monitoring_api_security, name='monitoring_api_security'),
    path('monitoring/api/uploads/', monitoring_views.monitoring_api_uploads, name='monitoring_api_uploads'),
    path('monitoring/api/logs/', monitoring_views.monitoring_api_logs, name='monitoring_api_logs'),
    path('monitoring/api/maintenance/', monitoring_views.monitoring_api_maintenance, name='monitoring_api_maintenance'),
]