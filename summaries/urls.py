"""
URL маршруты для приложения summaries (Своды)
"""
from django.urls import path
from . import views

app_name = 'summaries'

urlpatterns = [
    # Основные страницы
    path('', views.summary_list, name='summary_list'),
    path('<int:pk>/', views.summary_detail, name='summary_detail'),
    path('statistics/', views.summary_statistics, name='statistics'),
    path('help/', views.help_page, name='help'),
    
    # Создание и управление сводами
    path('create/<int:request_id>/', views.create_summary, name='create_summary'),
    path('<int:summary_id>/generate-file/', views.generate_summary_file, name='generate_summary_file'),
    path('<int:summary_id>/send-to-client/', views.send_summary_to_client, name='send_summary_to_client'),
    path('<int:summary_id>/change-status/', views.change_summary_status, name='change_summary_status'),
    
    # Управление предложениями
    path('<int:summary_id>/add-offer/', views.add_offer, name='add_offer'),
    path('offer/<int:offer_id>/edit/', views.edit_offer, name='edit_offer'),
    path('offer/<int:offer_id>/copy/', views.copy_offer, name='copy_offer'),
    path('offer/<int:offer_id>/delete/', views.delete_offer, name='delete_offer'),
    path('offer-search/', views.offer_search, name='offer_search'),
    
    # Загрузка ответов компаний
    path('<int:summary_id>/upload-company-response/', views.upload_company_response, name='upload_company_response'),
    path('<int:summary_id>/upload-multiple-company-responses/', views.upload_multiple_company_responses, name='upload_multiple_company_responses'),
]