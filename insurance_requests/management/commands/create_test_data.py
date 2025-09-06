"""
Команда для создания тестовых данных
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from insurance_requests.models import InsuranceRequest


class Command(BaseCommand):
    help = 'Создает тестовые данные для демонстрации системы'

    def handle(self, *args, **options):
        # Создаем несколько тестовых заявок
        test_requests = [
            {
                'client_name': 'ООО "Транспортная компания"',
                'inn': '1234567890',
                'insurance_type': 'КАСКО',
                'insurance_period': 12,
                'vehicle_info': 'Mercedes Sprinter 2021, VIN: WDB9066351234567',
                'has_franchise': True,
                'has_installment': False,
                'has_autostart': True,
                'status': 'uploaded'
            },
            {
                'client_name': 'ИП Иванов И.И.',
                'inn': '123456789012',
                'insurance_type': 'ОСАГО',
                'insurance_period': 12,
                'vehicle_info': 'Toyota Camry 2020, гос.номер А123БВ77',
                'has_franchise': False,
                'has_installment': True,
                'has_autostart': False,
                'status': 'email_generated'
            },
            {
                'client_name': 'ООО "Логистика Плюс"',
                'inn': '9876543210',
                'insurance_type': 'КАСКО',
                'insurance_period': 6,
                'vehicle_info': 'Volvo FH16 2022, прицеп в комплекте',
                'has_franchise': True,
                'has_installment': True,
                'has_autostart': False,
                'status': 'email_sent'
            }
        ]

        created_count = 0
        for data in test_requests:
            # Добавляем срок ответа (через неделю от текущей даты)
            data['response_deadline'] = timezone.now() + timedelta(days=7)
            
            request, created = InsuranceRequest.objects.get_or_create(
                client_name=data['client_name'],
                defaults=data
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Создана заявка: {request.client_name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Заявка уже существует: {request.client_name}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Создано {created_count} новых тестовых заявок')
        )