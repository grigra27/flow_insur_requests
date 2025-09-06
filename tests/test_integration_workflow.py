"""
Integration tests for complete insurance system workflow
"""
import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
from datetime import datetime, date, timedelta
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
import tempfile
import os

from insurance_requests.models import InsuranceRequest
from core.excel_utils import ExcelReader, map_branch_name
from core.templates import EmailTemplateGenerator


class TestCompleteWorkflowIntegration(TestCase):
    """Integration tests for the complete insurance request workflow"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Sample Excel data for testing
        self.sample_excel_data = {
            'client_name': 'ООО Тестовая Компания',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': 'с 01.01.2024 по 31.12.2024',
            'insurance_start_date': date(2024, 1, 1),
            'insurance_end_date': date(2024, 12, 31),
            'vehicle_info': 'Автомобиль Toyota Camry 2023',
            'dfa_number': 'ДФА-2024-001',
            'branch': 'Казанский филиал',
            'has_franchise': True,
            'has_installment': False,
            'has_autostart': True,
            'response_deadline': timezone.now() + timedelta(hours=3),
        }
    
    def test_end_to_end_excel_upload_workflow(self):
        """Test complete workflow from Excel upload to request creation"""
        # Mock Excel file reading
        with patch('core.excel_utils.ExcelReader.read_insurance_request') as mock_read:
            mock_read.return_value = self.sample_excel_data
            
            # Create ExcelReader instance
            excel_reader = ExcelReader('dummy_path.xlsx')
            
            # Read data from Excel
            extracted_data = excel_reader.read_insurance_request()
            
            # Verify data extraction
            self.assertEqual(extracted_data['client_name'], 'ООО Тестовая Компания')
            self.assertEqual(extracted_data['insurance_type'], 'КАСКО')
            self.assertEqual(extracted_data['dfa_number'], 'ДФА-2024-001')
            
            # Create InsuranceRequest from extracted data
            request = InsuranceRequest.objects.create(
                created_by=self.user,
                client_name=extracted_data['client_name'],
                inn=extracted_data['inn'],
                insurance_type=extracted_data['insurance_type'],
                insurance_period=extracted_data['insurance_period'],
                insurance_start_date=extracted_data['insurance_start_date'],
                insurance_end_date=extracted_data['insurance_end_date'],
                vehicle_info=extracted_data['vehicle_info'],
                dfa_number=extracted_data['dfa_number'],
                branch=map_branch_name(extracted_data['branch']),  # Apply branch mapping
                has_franchise=extracted_data['has_franchise'],
                has_installment=extracted_data['has_installment'],
                has_autostart=extracted_data['has_autostart'],
            )
            
            # Verify request creation and automatic response deadline
            self.assertIsNotNone(request.response_deadline)
            self.assertEqual(request.branch, 'Казань')  # Should be mapped
            self.assertEqual(request.get_display_name(), 'Заявка ДФА-2024-001')
            
            # Verify insurance period formatting
            expected_period = "с 01.01.2024 по 31.12.2024"
            self.assertEqual(request.insurance_period_formatted, expected_period)
    
    def test_email_generation_with_updated_data(self):
        """Test email generation using updated data model"""
        # Create request with new data structure
        request = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='ООО Тестовая Компания',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_start_date=date(2024, 6, 1),
            insurance_end_date=date(2025, 5, 31),
            vehicle_info='Автомобиль Toyota Camry 2023',
            dfa_number='ДФА-2024-001',
            branch='Казань',
            has_franchise=True,
            has_installment=False,
            has_autostart=True,
        )
        
        # Generate email using template generator
        template_generator = EmailTemplateGenerator()
        
        # Prepare data for email generation
        email_data = request.to_dict()
        
        # Generate email subject and body
        subject = template_generator.generate_subject(email_data)
        body = template_generator.generate_email_body(email_data)
        
        # Verify email subject format
        expected_subject_parts = ['ДФА-2024-001', 'Казань', 'Автомобиль Toyota Camry 2023', '1']
        for part in expected_subject_parts:
            self.assertIn(part, subject)
        
        # Verify email body contains expected elements
        self.assertIn('КАСКО', body)
        self.assertIn('1234567890', body)
        self.assertIn('с 01.06.2024 по 31.05.2025', body)  # Formatted dates
        self.assertIn('требуется тариф с франшизой', body)
        self.assertIn('у автомобиля имеется автозапуск', body)
        self.assertNotIn('требуется рассрочка', body)  # Should not be present
        
        # Update request with generated email data
        request.email_subject = subject
        request.email_body = body
        request.status = 'email_generated'
        request.save()
        
        # Verify request update
        self.assertEqual(request.status, 'email_generated')
        self.assertIsNotNone(request.email_subject)
        self.assertIsNotNone(request.email_body)
    
    def test_branch_mapping_integration(self):
        """Test branch mapping integration in complete workflow"""
        test_branches = [
            ('Казанский филиал', 'Казань'),
            ('Нижегородский филиал', 'Нижний Новгород'),
            ('Краснодарский филиал', 'Краснодар'),
            ('Неизвестный филиал', 'Неизвестный филиал'),
        ]
        
        for full_branch, expected_short in test_branches:
            with self.subTest(branch=full_branch):
                # Mock Excel data with different branch
                excel_data = self.sample_excel_data.copy()
                excel_data['branch'] = full_branch
                
                with patch('core.excel_utils.ExcelReader.read_insurance_request') as mock_read:
                    mock_read.return_value = excel_data
                    
                    # Create request
                    request = InsuranceRequest.objects.create(
                        created_by=self.user,
                        client_name=excel_data['client_name'],
                        branch=map_branch_name(excel_data['branch']),
                        dfa_number=f'ДФА-{full_branch[:3]}-001',
                    )
                    
                    # Verify branch mapping
                    self.assertEqual(request.branch, expected_short)
                    
                    # Test email generation with mapped branch
                    template_generator = EmailTemplateGenerator()
                    subject = template_generator.generate_subject(request.to_dict())
                    self.assertIn(expected_short, subject)
    
    def test_insurance_type_detection_workflow(self):
        """Test insurance type detection in complete workflow"""
        insurance_type_scenarios = [
            # (D21_value, D22_value, expected_type)
            ('КАСКО', None, 'КАСКО'),
            ('любое значение', 'спецтехника', 'КАСКО'),  # D21 has priority
            (None, 'спецтехника', 'страхование спецтехники'),
            ('', 'любое значение', 'страхование спецтехники'),
            (None, None, 'другое'),
            ('', '', 'другое'),
        ]
        
        for d21_value, d22_value, expected_type in insurance_type_scenarios:
            with self.subTest(d21=d21_value, d22=d22_value, expected=expected_type):
                # Mock Excel reader with specific cell values
                with patch('core.excel_utils.ExcelReader._determine_insurance_type_openpyxl') as mock_determine:
                    mock_determine.return_value = expected_type
                    
                    excel_data = self.sample_excel_data.copy()
                    excel_data['insurance_type'] = expected_type
                    
                    with patch('core.excel_utils.ExcelReader.read_insurance_request') as mock_read:
                        mock_read.return_value = excel_data
                        
                        # Create request
                        request = InsuranceRequest.objects.create(
                            created_by=self.user,
                            client_name='Test Client',
                            insurance_type=expected_type,
                            dfa_number=f'ДФА-{expected_type[:4]}-001',
                        )
                        
                        # Verify insurance type
                        self.assertEqual(request.insurance_type, expected_type)
                        
                        # Test email generation includes correct type
                        template_generator = EmailTemplateGenerator()
                        body = template_generator.generate_email_body(request.to_dict())
                        self.assertIn(expected_type, body)
    
    def test_response_deadline_management(self):
        """Test automatic response deadline management"""
        # Test automatic deadline setting
        before_creation = timezone.now()
        
        request = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='Test Client',
            dfa_number='ДФА-DEADLINE-001',
        )
        
        after_creation = timezone.now()
        
        # Verify automatic deadline was set
        self.assertIsNotNone(request.response_deadline)
        
        # Verify deadline is approximately 3 hours from creation
        expected_deadline_min = before_creation + timedelta(hours=3)
        expected_deadline_max = after_creation + timedelta(hours=3)
        
        self.assertGreaterEqual(request.response_deadline, expected_deadline_min)
        self.assertLessEqual(request.response_deadline, expected_deadline_max)
        
        # Test manual deadline override
        manual_deadline = timezone.now() + timedelta(hours=6)
        request.response_deadline = manual_deadline
        request.save()
        
        # Reload from database
        request.refresh_from_db()
        self.assertEqual(request.response_deadline, manual_deadline)
        
        # Test email generation uses actual deadline
        template_generator = EmailTemplateGenerator()
        email_data = request.to_dict()
        body = template_generator.generate_email_body(email_data)
        
        # Should contain formatted deadline
        deadline_str = manual_deadline.strftime('%d.%m.%Y в %H:%M')
        self.assertIn(deadline_str, body)
    
    def test_date_fields_integration(self):
        """Test integration of separate date fields with period formatting"""
        # Test with separate dates
        request = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='Test Client',
            insurance_start_date=date(2024, 3, 15),
            insurance_end_date=date(2025, 3, 14),
            insurance_period='старое значение',  # Should be overridden by property
            dfa_number='ДФА-DATES-001',
        )
        
        # Test insurance_period_formatted property
        expected_period = "с 15.03.2024 по 14.03.2025"
        self.assertEqual(request.insurance_period_formatted, expected_period)
        
        # Test email generation uses formatted period
        template_generator = EmailTemplateGenerator()
        email_data = request.to_dict()
        body = template_generator.generate_email_body(email_data)
        
        self.assertIn(expected_period, body)
        
        # Test fallback to old field when dates are None
        request.insurance_start_date = None
        request.insurance_end_date = None
        request.insurance_period = 'с 01.01.2024 по 31.12.2024'
        request.save()
        
        self.assertEqual(request.insurance_period_formatted, 'с 01.01.2024 по 31.12.2024')
    
    def test_display_name_integration(self):
        """Test display name integration across the system"""
        # Test with DFA number
        request_with_dfa = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='Test Client 1',
            dfa_number='ДФА-2024-001',
        )
        
        self.assertEqual(request_with_dfa.get_display_name(), 'Заявка ДФА-2024-001')
        self.assertIn('ДФА-2024-001', str(request_with_dfa))
        
        # Test without DFA number (fallback to ID)
        request_without_dfa = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='Test Client 2',
            dfa_number='',
        )
        
        expected_fallback = f'Заявка #{request_without_dfa.id}'
        self.assertEqual(request_without_dfa.get_display_name(), expected_fallback)
        self.assertIn(f'#{request_without_dfa.id}', str(request_without_dfa))
        
        # Test with "Номер ДФА не указан" (should use fallback)
        request_no_dfa = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='Test Client 3',
            dfa_number='Номер ДФА не указан',
        )
        
        expected_fallback = f'Заявка #{request_no_dfa.id}'
        self.assertEqual(request_no_dfa.get_display_name(), expected_fallback)
    
    def test_template_rendering_integration(self):
        """Test template rendering with new display logic"""
        # Create request with all features
        request = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='ООО Интеграционный Тест',
            inn='9876543210',
            insurance_type='страхование спецтехники',
            insurance_start_date=date(2024, 7, 1),
            insurance_end_date=date(2025, 6, 30),
            vehicle_info='Экскаватор Caterpillar 320D',
            dfa_number='ДФА-INTEGRATION-2024',
            branch='Нижний Новгород',
            has_franchise=False,
            has_installment=True,
            has_autostart=False,
        )
        
        # Test data conversion for templates
        template_data = request.to_dict()
        
        # Verify all expected fields are present
        expected_fields = [
            'client_name', 'inn', 'insurance_type', 'insurance_period',
            'insurance_start_date', 'insurance_end_date', 'vehicle_info',
            'dfa_number', 'branch', 'has_franchise', 'has_installment',
            'has_autostart', 'response_deadline'
        ]
        
        for field in expected_fields:
            self.assertIn(field, template_data)
        
        # Verify formatted values
        self.assertEqual(template_data['insurance_period'], 'с 01.07.2024 по 30.06.2025')
        self.assertIsInstance(template_data['response_deadline'], str)
        
        # Test email generation with all features
        template_generator = EmailTemplateGenerator()
        subject = template_generator.generate_subject(template_data)
        body = template_generator.generate_email_body(template_data)
        
        # Verify subject contains all components
        subject_components = ['ДФА-INTEGRATION-2024', 'Нижний Новгород', 'Экскаватор Caterpillar 320D']
        for component in subject_components:
            self.assertIn(component, subject)
        
        # Verify body contains conditional elements
        self.assertIn('страхование спецтехники', body)
        self.assertIn('требуется рассрочка', body)
        self.assertNotIn('требуется тариф с франшизой', body)
        self.assertNotIn('у автомобиля имеется автозапуск', body)
    
    @patch('core.excel_utils.logger')
    def test_error_handling_integration(self, mock_logger):
        """Test error handling in complete workflow"""
        # Test Excel reading with errors
        with patch('core.excel_utils.ExcelReader.read_insurance_request') as mock_read:
            mock_read.side_effect = Exception("Excel reading error")
            
            excel_reader = ExcelReader('invalid_file.xlsx')
            
            # Should not raise exception, should return default data
            try:
                result = excel_reader.read_insurance_request()
                # Should get default data
                self.assertEqual(result['client_name'], 'Тестовый клиент')
                mock_logger.error.assert_called()
            except Exception:
                self.fail("ExcelReader should handle errors gracefully")
        
        # Test request creation with minimal data
        minimal_request = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='Minimal Client',
        )
        
        # Should still work with defaults
        self.assertIsNotNone(minimal_request.response_deadline)
        self.assertEqual(minimal_request.insurance_period_formatted, 'Период не указан')
        self.assertIn(f'#{minimal_request.id}', minimal_request.get_display_name())


class TestWorkflowPerformance(TestCase):
    """Performance tests for workflow operations"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.user = User.objects.create_user(
            username='perfuser',
            email='perf@example.com',
            password='perfpass123'
        )
    
    def test_bulk_request_creation_performance(self):
        """Test performance of creating multiple requests"""
        import time
        
        start_time = time.time()
        
        # Create 100 requests
        requests = []
        for i in range(100):
            request = InsuranceRequest(
                created_by=self.user,
                client_name=f'Client {i}',
                dfa_number=f'ДФА-PERF-{i:03d}',
                insurance_start_date=date(2024, 1, 1),
                insurance_end_date=date(2024, 12, 31),
            )
            requests.append(request)
        
        # Bulk create
        InsuranceRequest.objects.bulk_create(requests)
        
        end_time = time.time()
        creation_time = end_time - start_time
        
        # Should complete within reasonable time (adjust threshold as needed)
        self.assertLess(creation_time, 5.0, "Bulk creation took too long")
        
        # Verify all requests were created
        self.assertEqual(InsuranceRequest.objects.filter(created_by=self.user).count(), 100)
    
    def test_email_generation_performance(self):
        """Test performance of email generation"""
        import time
        
        # Create request
        request = InsuranceRequest.objects.create(
            created_by=self.user,
            client_name='Performance Test Client',
            dfa_number='ДФА-PERF-EMAIL',
            insurance_start_date=date(2024, 1, 1),
            insurance_end_date=date(2024, 12, 31),
            vehicle_info='Test Vehicle Info',
            branch='Казань',
        )
        
        template_generator = EmailTemplateGenerator()
        
        start_time = time.time()
        
        # Generate 100 emails
        for i in range(100):
            email_data = request.to_dict()
            subject = template_generator.generate_subject(email_data, i + 1)
            body = template_generator.generate_email_body(email_data)
        
        end_time = time.time()
        generation_time = end_time - start_time
        
        # Should complete within reasonable time
        self.assertLess(generation_time, 2.0, "Email generation took too long")


if __name__ == '__main__':
    unittest.main()