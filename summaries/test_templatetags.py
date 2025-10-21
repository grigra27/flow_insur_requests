"""
Tests for summary templatetags
"""
from django.test import TestCase
from summaries.templatetags.summary_extras import (
    status_color, format_branch, status_display_name,
    companies_count_badge_class, companies_count_size_class
)


class SummaryTemplatetagsTest(TestCase):
    """Test cases for summary templatetags"""
    
    def test_status_color_filter(self):
        """Test status_color filter returns correct Bootstrap colors"""
        # Test all valid statuses
        self.assertEqual(status_color('collecting'), 'warning')
        self.assertEqual(status_color('ready'), 'info')
        self.assertEqual(status_color('sent'), 'success')
        self.assertEqual(status_color('completed'), 'secondary')
        
        # Test invalid status returns default
        self.assertEqual(status_color('invalid_status'), 'secondary')
        self.assertEqual(status_color(None), 'secondary')
        self.assertEqual(status_color(''), 'secondary')
    
    def test_format_branch_filter(self):
        """Test format_branch filter formats branch names correctly"""
        # Test normal branch name
        self.assertEqual(format_branch('Москва'), 'Москва')
        self.assertEqual(format_branch('  Санкт-Петербург  '), 'Санкт-Петербург')
        
        # Test empty/None values
        self.assertEqual(format_branch(None), 'Не указан')
        self.assertEqual(format_branch(''), 'Не указан')
        self.assertEqual(format_branch('   '), 'Не указан')
    

    def test_status_display_name_filter(self):
        """Test status_display_name filter returns correct status names"""
        # Test all valid statuses
        self.assertEqual(status_display_name('collecting'), 'Сбор предложений')
        self.assertEqual(status_display_name('ready'), 'Готов к отправке')
        self.assertEqual(status_display_name('sent'), 'Отправлен в Альянс')  # Updated name
        self.assertEqual(status_display_name('completed'), 'Завершен')
        
        # Test invalid status returns original value
        self.assertEqual(status_display_name('invalid_status'), 'invalid_status')
        self.assertEqual(status_display_name(None), None)
        self.assertEqual(status_display_name(''), '')

    def test_companies_count_badge_class_filter(self):
        """Test companies_count_badge_class filter returns correct CSS classes"""
        # Test color scheme based on count ranges
        self.assertEqual(companies_count_badge_class(0), 'bg-secondary')  # Gray for 0
        self.assertEqual(companies_count_badge_class(1), 'bg-warning text-dark')  # Yellow for 1-2
        self.assertEqual(companies_count_badge_class(2), 'bg-warning text-dark')  # Yellow for 1-2
        self.assertEqual(companies_count_badge_class(3), 'bg-info text-dark')  # Blue for 3-4
        self.assertEqual(companies_count_badge_class(4), 'bg-info text-dark')  # Blue for 3-4
        self.assertEqual(companies_count_badge_class(5), 'bg-success')  # Green for 5-6
        self.assertEqual(companies_count_badge_class(6), 'bg-success')  # Green for 5-6
        self.assertEqual(companies_count_badge_class(7), 'bg-primary')  # Purple for 7+
        self.assertEqual(companies_count_badge_class(10), 'bg-primary')  # Purple for 7+
        
        # Test edge cases
        self.assertEqual(companies_count_badge_class(None), 'bg-secondary')
        self.assertEqual(companies_count_badge_class(''), 'bg-secondary')
        self.assertEqual(companies_count_badge_class('invalid'), 'bg-secondary')

    def test_companies_count_size_class_filter(self):
        """Test companies_count_size_class filter returns correct size CSS classes"""
        # Test size classes based on count ranges
        self.assertEqual(companies_count_size_class(0), 'fs-6')  # Normal size for 0-4
        self.assertEqual(companies_count_size_class(4), 'fs-6')  # Normal size for 0-4
        self.assertEqual(companies_count_size_class(5), 'fs-6 fw-semibold')  # Medium size for 5-9
        self.assertEqual(companies_count_size_class(9), 'fs-6 fw-semibold')  # Medium size for 5-9
        self.assertEqual(companies_count_size_class(10), 'fs-5 fw-bold')  # Large size for 10+
        self.assertEqual(companies_count_size_class(15), 'fs-5 fw-bold')  # Large size for 10+
        
        # Test edge cases
        self.assertEqual(companies_count_size_class(None), 'fs-6')
        self.assertEqual(companies_count_size_class(''), 'fs-6')
        self.assertEqual(companies_count_size_class('invalid'), 'fs-6')