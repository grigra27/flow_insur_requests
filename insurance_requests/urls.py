"""
URL маршруты для приложения insurance_requests
"""
from django.urls import path
from . import views

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
    path('<int:pk>/change-status/', views.change_request_status, name='change_request_status'),

]