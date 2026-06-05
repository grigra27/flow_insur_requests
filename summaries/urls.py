"""
URL маршруты для приложения summaries (Своды)
"""
from django.urls import path
from . import views

app_name = 'summaries'

urlpatterns = [
    # Основные страницы
    path('', views.summary_list, name='summary_list'),
    path('deals/', views.deal_list, name='deal_list'),
    path('<int:pk>/', views.summary_detail, name='summary_detail'),
    path('<int:summary_id>/deal-summary/', views.deal_summary, name='deal_summary'),
    path('statistics/', views.summary_statistics, name='statistics'),
    path('statistics/export/', views.export_statistics_widget, name='export_statistics_widget'),
    path('analytics/', views.analytics_placeholder, name='analytics'),
    path('analytics/parser-edits/', views.analytics_parser_edits, name='analytics_parser_edits'),
    path('analytics/post-creation/', views.analytics_post_creation, name='analytics_post_creation'),
    path('analytics/insurance-offers/', views.analytics_insurance_offers, name='analytics_insurance_offers'),
    path('analytics/insurance-companies/', views.analytics_insurance_companies, name='analytics_insurance_companies'),
    path('analytics/insurance-companies/export/', views.export_analytics_insurance_companies_widget, name='export_analytics_insurance_companies_widget'),
    path('analytics/managers/', views.analytics_managers, name='analytics_managers'),
    path('analytics/managers/compare/', views.analytics_managers_compare, name='analytics_managers_compare'),
    path('analytics/managers/leaderboard/', views.analytics_managers_leaderboard, name='analytics_managers_leaderboard'),
    path('analytics/managers/export/', views.export_analytics_managers_widget, name='export_analytics_managers_widget'),
    path('analytics/managers/<int:user_id>/', views.analytics_manager_detail, name='analytics_manager_detail'),
    path('analytics/managers/<int:user_id>/export/', views.export_analytics_managers_widget, name='export_analytics_manager_detail'),
    path('help/', views.help_page, name='help'),
    
    # Создание и управление сводами
    path('create/<int:request_id>/', views.create_summary, name='create_summary'),
    path('<int:summary_id>/generate-file/', views.generate_summary_file, name='generate_summary_file'),
    path('<int:summary_id>/generate-client-file/', views.generate_client_summary_file, name='generate_client_summary_file'),
    path('<int:summary_id>/send-to-client/', views.send_summary_to_client, name='send_summary_to_client'),
    path('<int:summary_id>/change-status/', views.change_summary_status, name='change_summary_status'),
    path('<int:summary_id>/update-notes/', views.update_summary_notes, name='update_summary_notes'),
    
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
