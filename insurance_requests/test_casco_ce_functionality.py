"""
Unit tests for КАСКО C/E functionality
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from insurance_requests.models import InsuranceRequest
from insurance_requests.forms import InsuranceRequestForm
from core.templates import EmailTemplateGenerator


class CascoCEModelTest(TestCase):
    """Tests for КАСКО C/E field in InsuranceRequest model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.request_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'vehicle_info': 'Test Vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Казань',
            'created_by': self.user,
        }
    
    def test_has_casco_ce_field_exists(self):
        """Test that has_casco_ce field exists and has correct default value"""
        request = InsuranceRequest.objects.create(**self.request_data)
        
        # Check field exists and has default value False
        self.assertFalse(request.has_casco_ce)
        self.assertEqual(request._meta.get_field('has_casco_ce').verbose_name, 'КАСКО кат. C/E')
    
    def test_has_casco_ce_can_be_set_true(self):
        """Test that has_casco_ce field can be set to True"""
        self.request_data['has_casco_ce'] = True
        request = InsuranceRequest.objects.create(**self.request_data)
        
        self.assertTrue(request.has_casco_ce)
    
    def test_has_casco_ce_can_be_set_false(self):
        """Test that has_casco_ce field can be explicitly set to False"""
        self.request_data['has_casco_ce'] = False
        request = InsuranceRequest.objects.create(**self.request_data)
        
        self.assertFalse(request.has_casco_ce)
    
    def test_to_dict_includes_has_casco_ce_false(self):
        """Test that to_dict method includes has_casco_ce field when False"""
        request = InsuranceRequest.objects.create(**self.request_data)
        data_dict = request.to_dict()
        
        self.assertIn('has_casco_ce', data_dict)
        self.assertFalse(data_dict['has_casco_ce'])
    
    def test_to_dict_includes_has_casco_ce_true(self):
        """Test that to_dict method includes has_casco_ce field when True"""
        self.request_data['has_casco_ce'] = True
        request = InsuranceRequest.objects.create(**self.request_data)
        data_dict = request.to_dict()
        
        self.assertIn('has_casco_ce', data_dict)
        self.assertTrue(data_dict['has_casco_ce'])


class CascoCEFormTest(TestCase):
    """Tests for КАСКО C/E field in InsuranceRequestForm"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        self.form_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': '1 год',
            'vehicle_info': 'Test Vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Казань',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'response_deadline': timezone.now() + timedelta(hours=3),
        }
    
    def test_form_includes_has_casco_ce_field(self):
        """Test that form includes has_casco_ce field"""
        form = InsuranceRequestForm()
        
        self.assertIn('has_casco_ce', form.fields)
        self.assertEqual(form.fields['has_casco_ce'].required, False)
    
    def test_form_valid_with_has_casco_ce_false(self):
        """Test that form is valid with has_casco_ce set to False"""
        self.form_data['has_casco_ce'] = False
        form = InsuranceRequestForm(data=self.form_data)
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_form_valid_with_has_casco_ce_true(self):
        """Test that form is valid with has_casco_ce set to True"""
        self.form_data['has_casco_ce'] = True
        form = InsuranceRequestForm(data=self.form_data)
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_form_valid_without_has_casco_ce(self):
        """Test that form is valid when has_casco_ce is not provided (defaults to False)"""
        # Don't include has_casco_ce in form data
        form = InsuranceRequestForm(data=self.form_data)
        
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
    
    def test_form_saves_has_casco_ce_false(self):
        """Test that form correctly saves has_casco_ce as False"""
        self.form_data['has_casco_ce'] = False
        form = InsuranceRequestForm(data=self.form_data)
        
        self.assertTrue(form.is_valid())
        instance = form.save(commit=False)
        instance.created_by = self.user
        instance.save()
        
        self.assertFalse(instance.has_casco_ce)
    
    def test_form_saves_has_casco_ce_true(self):
        """Test that form correctly saves has_casco_ce as True"""
        self.form_data['has_casco_ce'] = True
        form = InsuranceRequestForm(data=self.form_data)
        
        self.assertTrue(form.is_valid())
        instance = form.save(commit=False)
        instance.created_by = self.user
        instance.save()
        
        self.assertTrue(instance.has_casco_ce)
    
    def test_form_widget_is_checkbox(self):
        """Test that has_casco_ce field uses CheckboxInput widget"""
        form = InsuranceRequestForm()
        widget = form.fields['has_casco_ce'].widget
        
        self.assertEqual(widget.__class__.__name__, 'CheckboxInput')
        self.assertIn('form-check-input', widget.attrs.get('class', ''))


class CascoCEEmailTemplateTest(TestCase):
    """Tests for КАСКО C/E parameter in email template generation"""
    
    def setUp(self):
        """Set up test data"""
        self.generator = EmailTemplateGenerator()
        
        self.base_data = {
            'client_name': 'Test Client',
            'inn': '1234567890',
            'insurance_type': 'КАСКО',
            'insurance_period': 'на весь срок лизинга',
            'vehicle_info': 'Test Vehicle',
            'dfa_number': 'DFA123',
            'branch': 'Казань',
            'has_franchise': False,
            'has_installment': False,
            'has_autostart': False,
            'response_deadline': '01.01.2024 в 15:00',
        }
    
    def test_casco_type_ce_empty_when_false(self):
        """Test that casco_type_ce parameter is empty when has_casco_ce is False"""
        self.base_data['has_casco_ce'] = False
        template_data = self.generator._prepare_template_data(self.base_data)
        
        self.assertIn('casco_type_ce', template_data)
        self.assertEqual(template_data['casco_type_ce'], '')
    
    def test_casco_type_ce_text_when_true(self):
        """Test that casco_type_ce parameter contains correct text when has_casco_ce is True"""
        self.base_data['has_casco_ce'] = True
        template_data = self.generator._prepare_template_data(self.base_data)
        
        self.assertIn('casco_type_ce', template_data)
        self.assertEqual(template_data['casco_type_ce'], ' это КАСКО С и Е')
    
    def test_casco_type_ce_empty_when_not_provided(self):
        """Test that casco_type_ce parameter is empty when has_casco_ce is not provided"""
        # Don't include has_casco_ce in data
        template_data = self.generator._prepare_template_data(self.base_data)
        
        self.assertIn('casco_type_ce', template_data)
        self.assertEqual(template_data['casco_type_ce'], '')
    
    def test_email_body_includes_casco_type_ce_when_false(self):
        """Test that generated email body correctly handles casco_type_ce when False"""
        self.base_data['has_casco_ce'] = False
        email_body = self.generator.generate_email_body(self.base_data)
        
        # Should not contain the КАСКО C/E text
        self.assertNotIn(' это КАСКО С и Е', email_body)
        # Should contain the insurance type description
        self.assertIn('по КАСКО', email_body)
    
    def test_email_body_includes_casco_type_ce_when_true(self):
        """Test that generated email body correctly includes casco_type_ce when True"""
        self.base_data['has_casco_ce'] = True
        email_body = self.generator.generate_email_body(self.base_data)
        
        # Should contain the КАСКО C/E text
        self.assertIn(' это КАСКО С и Е', email_body)
        # Should contain the insurance type description
        self.assertIn('по КАСКО', email_body)
    
    def test_email_template_format_with_casco_ce(self):
        """Test that email template correctly formats with casco_type_ce parameter"""
        self.base_data['has_casco_ce'] = True
        email_body = self.generator.generate_email_body(self.base_data)
        
        # Check that the email body contains both the insurance type and casco_type_ce text
        self.assertIn('по КАСКО', email_body)
        self.assertIn(' это КАСКО С и Е', email_body)
        
        # The casco_type_ce text should appear after the insurance type description
        casco_pos = email_body.find(' это КАСКО С и Е')
        kasko_pos = email_body.find('по КАСКО')
        self.assertGreater(casco_pos, kasko_pos)
    
    def test_backward_compatibility_without_casco_ce(self):
        """Test that email generation works correctly for old requests without has_casco_ce field"""
        # Simulate old request data without has_casco_ce field
        old_data = self.base_data.copy()
        # Don't include has_casco_ce at all
        
        email_body = self.generator.generate_email_body(old_data)
        
        # Should generate email without errors
        self.assertIsInstance(email_body, str)
        self.assertIn('Высылаем заявку на расчет тарифов', email_body)
        self.assertNotIn(' это КАСКО С и Е', email_body)


class CascoCEIntegrationTest(TestCase):
    """Integration tests for КАСКО C/E functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_full_workflow_with_casco_ce_true(self):
        """Test complete workflow from model creation to email generation with КАСКО C/E enabled"""
        # Create request with КАСКО C/E enabled
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='1 год',
            vehicle_info='Test Vehicle',
            dfa_number='DFA123',
            branch='Казань',
            has_casco_ce=True,
            created_by=self.user,
        )
        
        # Convert to dict (as used in email generation)
        data_dict = request.to_dict()
        
        # Generate email
        generator = EmailTemplateGenerator()
        email_body = generator.generate_email_body(data_dict)
        
        # Verify the complete workflow
        self.assertTrue(request.has_casco_ce)
        self.assertTrue(data_dict['has_casco_ce'])
        self.assertIn(' это КАСКО С и Е', email_body)
        self.assertIn('по КАСКО', email_body)
    
    def test_full_workflow_with_casco_ce_false(self):
        """Test complete workflow from model creation to email generation with КАСКО C/E disabled"""
        # Create request with КАСКО C/E disabled
        request = InsuranceRequest.objects.create(
            client_name='Test Client',
            inn='1234567890',
            insurance_type='КАСКО',
            insurance_period='на весь срок лизинга',
            vehicle_info='Test Vehicle',
            dfa_number='DFA123',
            branch='Казань',
            has_casco_ce=False,
            created_by=self.user,
        )
        
        # Convert to dict (as used in email generation)
        data_dict = request.to_dict()
        
        # Generate email
        generator = EmailTemplateGenerator()
        email_body = generator.generate_email_body(data_dict)
        
        # Verify the complete workflow
        self.assertFalse(request.has_casco_ce)
        self.assertFalse(data_dict['has_casco_ce'])
        self.assertNotIn(' это КАСКО С и Е', email_body)
        self.assertIn('по КАСКО', email_body)