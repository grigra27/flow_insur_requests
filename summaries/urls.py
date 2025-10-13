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
    
    # Создание и управление сводами
    path('create/<int:request_id>/', views.create_summary, name='create_summary'),
    path('create_from_offers/<int:request_id>/', views.create_summary_from_offers, name='create_summary_from_offers'),
    path('<int:summary_id>/generate-file/', views.generate_summary_file, name='generate_summary_file'),
    path('<int:summary_id>/send-to-client/', views.send_summary_to_client, name='send_summary_to_client'),
    
    # Управление предложениями
    path('<int:summary_id>/add-offer/', views.add_offer, name='add_offer'),
    path('offer/<int:offer_id>/edit/', views.edit_offer, name='edit_offer'),
    path('offer/<int:offer_id>/delete/', views.delete_offer, name='delete_offer'),
]