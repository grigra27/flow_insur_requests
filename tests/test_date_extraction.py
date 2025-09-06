"""
Unit tests for date extraction and formatting functionality
"""
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, date
from core.excel_utils import ExcelReader
from insurance_requests.models import InsuranceRequest


class TestDateExtraction(unittest.TestCase):
    """Test cases for date extraction and formatting"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.excel_reader = ExcelReader("dummy_path.xlsx")
    
    def test_parse_date_dd_mm_yyyy_format(self):
        """Test parsing dates in DD.MM.YYYY format"""
        test_cases = [
            ("01.01.2024", date(2024, 1, 1)),
            ("15.06.2025", date(2025, 6, 15)),
            ("31.12.2023", date(2023, 12, 31)),
            ("29.02.2024", date(2024, 2, 29)),  # Leap year
        ]
        
        for date_str, expected_date in test_cases:
            with self.subTest(date_str=date_str):
                result = self.excel_reader._parse_date(date_str)
                self.assertEqual(result, expected_date)
    
    def test_parse_date_yyyy_mm_dd_format(self):
        """Test parsing dates in YYYY-MM-DD format"""
        test_cases = [
            ("2024-01-01", date(2024, 1, 1)),
            ("2025-06-15", date(2025, 6, 15)),
            ("2023-12-31", date(2023, 12, 31)),
            ("2024-02-29", date(2024, 2, 29)),  # Leap year
        ]
        
        for date_str, expected_date in test_cases:
            with self.subTest(date_str=date_str):
                result = self.excel_reader._parse_date(date_str)
                self.assertEqual(result, expected_date)
    
    def test_parse_date_dd_slash_mm_yyyy_format(self):
        """Test parsing dates in DD/MM/YYYY format"""
        test_cases = [
            ("01/01/2024", date(2024, 1, 1)),
            ("15/06/2025", date(2025, 6, 15)),
            ("31/12/2023", date(2023, 12, 31)),
        ]
        
        for date_str, expected_date in test_cases:
            with self.subTest(date_str=date_str):
                result = self.excel_reader._parse_date(date_str)
                self.assertEqual(result, expected_date)
    
    def test_parse_date_mm_slash_dd_yyyy_format(self):
        """Test parsing dates in MM/DD/YYYY format"""
        test_cases = [
            ("01/15/2024", date(2024, 1, 15)),
            ("06/30/2025", date(2025, 6, 30)),
            ("12/25/2023", date(2023, 12, 25)),
        ]
        
        for date_str, expected_date in test_cases:
            with self.subTest(date_str=date_str):
                result = self.excel_reader._parse_date(date_str)
                self.assertEqual(result, expected_date)
    
    def test_parse_date_two_digit_year(self):
        """Test parsing dates with two-digit years"""
        test_cases = [
            ("01.01.24", date(2024, 1, 1)),
            ("15/06/25", date(2025, 6, 15)),
        ]
        
        for date_str, expected_date in test_cases:
            with self.subTest(date_str=date_str):
                result = self.excel_reader._parse_date(date_str)
                self.assertEqual(result, expected_date)
    
    def test_parse_date_datetime_objects(self):
        """Test parsing datetime objects"""
        test_datetime = datetime(2024, 6, 15, 10, 30, 45)
        expected_date = date(2024, 6, 15)
        
        result = self.excel_reader._parse_date(test_datetime)
        self.assertEqual(result, expected_date)
    
    def test_parse_date_date_objects(self):
        """Test parsing date objects (should return as-is)"""
        test_date = date(2024, 6, 15)
        
        result = self.excel_reader._parse_date(test_date)
        self.assertEqual(result, test_date)
    
    def test_parse_date_invalid_formats(self):
        """Test parsing invalid date formats returns None"""
        invalid_dates = [
            "invalid_date",
            "32.01.2024",  # Invalid day
            "01.13.2024",  # Invalid month
            "29.02.2023",  # Invalid leap year
            "abc.def.ghij",
            "2024/13/01",  # Invalid month
            "",
            "   ",
        ]
        
        for invalid_date in invalid_dates:
            with self.subTest(invalid_date=invalid_date):
                result = self.excel_reader._parse_date(invalid_date)
                self.assertIsNone(result)
    
    def test_parse_date_none_and_empty(self):
        """Test parsing None and empty values"""
        test_cases = [None, "", "   ", "none", "nan", "NaN"]
        
        for test_value in test_cases:
            with self.subTest(test_value=repr(test_value)):
                result = self.excel_reader._parse_date(test_value)
                self.assertIsNone(result)
    
    @patch('core.excel_utils.logger')
    def test_parse_date_logging(self, mock_logger):
        """Test that unparseable dates are logged"""
        self.excel_reader._parse_date("invalid_date")
        mock_logger.warning.assert_called_with("Could not parse date: invalid_date")
    
    def test_format_insurance_period_valid_dates(self):
        """Test formatting insurance period with valid dates"""
        test_cases = [
            ("01.01.2024", "31.12.2024", "с 01.01.2024 по 31.12.2024"),
            ("15.06.2025", "15.06.2026", "с 15.06.2025 по 15.06.2026"),
            ("2024-01-01", "2024-12-31", "с 01.01.2024 по 31.12.2024"),
        ]
        
        for start_date, end_date, expected_period in test_cases:
            with self.subTest(start_date=start_date, end_date=end_date):
                result = self.excel_reader._format_insurance_period(start_date, end_date)
                self.assertEqual(result, expected_period)
    
    def test_format_insurance_period_missing_dates(self):
        """Test formatting insurance period with missing dates"""
        test_cases = [
            (None, "31.12.2024"),
            ("01.01.2024", None),
            (None, None),
            ("", "31.12.2024"),
            ("01.01.2024", ""),
        ]
        
        for start_date, end_date in test_cases:
            with self.subTest(start_date=start_date, end_date=end_date):
                result = self.excel_reader._format_insurance_period(start_date, end_date)
                self.assertEqual(result, "с 01.01.2024 по 01.01.2025")
    
    def test_format_insurance_period_invalid_dates(self):
        """Test formatting insurance period with invalid dates"""
        result = self.excel_reader._format_insurance_period("invalid_start", "invalid_end")
        self.assertEqual(result, "с invalid_start по invalid_end")
    
    def test_parse_and_format_date_valid(self):
        """Test parse and format date with valid inputs"""
        test_cases = [
            ("01.01.2024", "01.01.2024"),
            ("2024-01-01", "01.01.2024"),
            ("01/01/2024", "01.01.2024"),
            ("1/15/2024", "15.01.2024"),  # MM/DD/YYYY format
        ]
        
        for input_date, expected_output in test_cases:
            with self.subTest(input_date=input_date):
                result = self.excel_reader._parse_and_format_date(input_date)
                self.assertEqual(result, expected_output)
    
    def test_parse_and_format_date_invalid(self):
        """Test parse and format date with invalid inputs"""
        test_cases = [
            ("invalid_date", "invalid_date"),
            ("", "01.01.2024"),
            (None, "01.01.2024"),
        ]
        
        for input_date, expected_output in test_cases:
            with self.subTest(input_date=input_date):
                result = self.excel_reader._parse_and_format_date(input_date)
                self.assertEqual(result, expected_output)


class TestInsuranceRequestDateFormatting(unittest.TestCase):
    """Test cases for InsuranceRequest model date formatting"""
    
    def test_insurance_period_formatted_with_dates(self):
        """Test insurance_period_formatted property with separate dates"""
        request = InsuranceRequest(
            insurance_start_date=date(2024, 1, 1),
            insurance_end_date=date(2024, 12, 31),
            insurance_period="старое значение"
        )
        
        result = request.insurance_period_formatted
        self.assertEqual(result, "с 01.01.2024 по 31.12.2024")
    
    def test_insurance_period_formatted_fallback_to_old_field(self):
        """Test insurance_period_formatted falls back to old field when dates are None"""
        request = InsuranceRequest(
            insurance_start_date=None,
            insurance_end_date=None,
            insurance_period="с 15.06.2024 по 15.06.2025"
        )
        
        result = request.insurance_period_formatted
        self.assertEqual(result, "с 15.06.2024 по 15.06.2025")
    
    def test_insurance_period_formatted_no_data(self):
        """Test insurance_period_formatted when no data is available"""
        request = InsuranceRequest(
            insurance_start_date=None,
            insurance_end_date=None,
            insurance_period=""
        )
        
        result = request.insurance_period_formatted
        self.assertEqual(result, "Период не указан")
    
    def test_insurance_period_formatted_partial_dates(self):
        """Test insurance_period_formatted with only one date available"""
        # Only start date
        request1 = InsuranceRequest(
            insurance_start_date=date(2024, 1, 1),
            insurance_end_date=None,
            insurance_period="fallback period"
        )
        
        result1 = request1.insurance_period_formatted
        self.assertEqual(result1, "fallback period")
        
        # Only end date
        request2 = InsuranceRequest(
            insurance_start_date=None,
            insurance_end_date=date(2024, 12, 31),
            insurance_period="fallback period"
        )
        
        result2 = request2.insurance_period_formatted
        self.assertEqual(result2, "fallback period")


class TestDateExtractionIntegration(unittest.TestCase):
    """Integration tests for date extraction in Excel reading"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.excel_reader = ExcelReader("dummy_path.xlsx")
    
    def test_extract_data_openpyxl_date_extraction(self):
        """Test date extraction in openpyxl data extraction"""
        mock_sheet = Mock()
        
        with patch.object(self.excel_reader, '_get_cell_value') as mock_get_cell:
            with patch.object(self.excel_reader, '_determine_insurance_type_openpyxl'):
                with patch.object(self.excel_reader, '_find_leasing_object_info_openpyxl'):
                    with patch.object(self.excel_reader, '_find_dfa_number_openpyxl'):
                        with patch.object(self.excel_reader, '_find_branch_openpyxl'):
                            # Mock date cells M15 and N15
                            mock_get_cell.side_effect = lambda sheet, cell: (
                                "01.01.2024" if cell == 'M15' else
                                "31.12.2024" if cell == 'N15' else
                                "test_value"
                            )
                            
                            result = self.excel_reader._extract_data_openpyxl(mock_sheet)
                            
                            self.assertEqual(result['insurance_start_date'], date(2024, 1, 1))
                            self.assertEqual(result['insurance_end_date'], date(2024, 12, 31))
                            self.assertEqual(result['insurance_period'], "с 01.01.2024 по 31.12.2024")
    
    def test_extract_data_pandas_date_extraction(self):
        """Test date extraction in pandas data extraction"""
        mock_df = Mock()
        
        with patch.object(self.excel_reader, '_safe_get_cell') as mock_safe_get:
            with patch.object(self.excel_reader, '_determine_insurance_type_pandas'):
                with patch.object(self.excel_reader, '_find_leasing_object_info_pandas'):
                    with patch.object(self.excel_reader, '_find_dfa_number_pandas'):
                        with patch.object(self.excel_reader, '_find_branch_pandas'):
                            # Mock date cells M15 (14, 12) and N15 (14, 13)
                            mock_safe_get.side_effect = lambda df, row, col: (
                                "01.01.2024" if (row, col) == (14, 12) else
                                "31.12.2024" if (row, col) == (14, 13) else
                                "test_value"
                            )
                            
                            result = self.excel_reader._extract_data_pandas(mock_df)
                            
                            self.assertEqual(result['insurance_start_date'], date(2024, 1, 1))
                            self.assertEqual(result['insurance_end_date'], date(2024, 12, 31))
                            self.assertEqual(result['insurance_period'], "с 01.01.2024 по 31.12.2024")
    
    def test_date_extraction_with_invalid_dates(self):
        """Test date extraction handles invalid dates gracefully"""
        mock_sheet = Mock()
        
        with patch.object(self.excel_reader, '_get_cell_value') as mock_get_cell:
            with patch.object(self.excel_reader, '_determine_insurance_type_openpyxl'):
                with patch.object(self.excel_reader, '_find_leasing_object_info_openpyxl'):
                    with patch.object(self.excel_reader, '_find_dfa_number_openpyxl'):
                        with patch.object(self.excel_reader, '_find_branch_openpyxl'):
                            # Mock invalid date cells
                            mock_get_cell.side_effect = lambda sheet, cell: (
                                "invalid_start_date" if cell == 'M15' else
                                "invalid_end_date" if cell == 'N15' else
                                "test_value"
                            )
                            
                            result = self.excel_reader._extract_data_openpyxl(mock_sheet)
                            
                            self.assertIsNone(result['insurance_start_date'])
                            self.assertIsNone(result['insurance_end_date'])
                            self.assertEqual(result['insurance_period'], "с invalid_start_date по invalid_end_date")


if __name__ == '__main__':
    unittest.main()