"""
Tests for new period determination logic using N17/N18 checkboxes
"""
import unittest
from unittest.mock import Mock, patch
from core.excel_utils import ExcelReader


class TestNewPeriodLogic(unittest.TestCase):
    """Test the new N17/N18 period determination logic"""
    
    def setUp(self):
        self.excel_reader = ExcelReader("dummy_path.xlsx")
    
    def test_determine_insurance_period_openpyxl_n17_has_value(self):
        """Test that N17 with value returns '1 год'"""
        mock_sheet = Mock()
        
        # Mock _get_cell_value to return values for N17 and N18
        def mock_get_cell_value(sheet, cell_address):
            if cell_address == 'N17':
                return 'X'  # Has value
            elif cell_address == 'N18':
                return None  # Empty
            return None
        
        with patch.object(self.excel_reader, '_get_cell_value', side_effect=mock_get_cell_value):
            result = self.excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "1 год")
    
    def test_determine_insurance_period_openpyxl_n18_has_value(self):
        """Test that N18 with value (and N17 empty) returns 'на весь срок лизинга'"""
        mock_sheet = Mock()
        
        def mock_get_cell_value(sheet, cell_address):
            if cell_address == 'N17':
                return None  # Empty
            elif cell_address == 'N18':
                return 'X'  # Has value
            return None
        
        with patch.object(self.excel_reader, '_get_cell_value', side_effect=mock_get_cell_value):
            result = self.excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "на весь срок лизинга")
    
    def test_determine_insurance_period_openpyxl_both_empty(self):
        """Test that both N17 and N18 empty returns empty string"""
        mock_sheet = Mock()
        
        def mock_get_cell_value(sheet, cell_address):
            if cell_address in ['N17', 'N18']:
                return None  # Both empty
            return None
        
        with patch.object(self.excel_reader, '_get_cell_value', side_effect=mock_get_cell_value):
            result = self.excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "")
    
    def test_determine_insurance_period_openpyxl_n17_priority(self):
        """Test that N17 takes priority over N18 when both have values"""
        mock_sheet = Mock()
        
        def mock_get_cell_value(sheet, cell_address):
            if cell_address == 'N17':
                return 'X'  # Has value
            elif cell_address == 'N18':
                return 'Y'  # Also has value
            return None
        
        with patch.object(self.excel_reader, '_get_cell_value', side_effect=mock_get_cell_value):
            result = self.excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "1 год")  # N17 should take priority
    
    def test_determine_insurance_period_pandas_n17_has_value(self):
        """Test pandas version with N17 having value"""
        mock_df = Mock()
        
        def mock_safe_get_cell(df, row, col):
            if row == 16 and col == 13:  # N17
                return 'X'
            elif row == 17 and col == 13:  # N18
                return None
            return None
        
        with patch.object(self.excel_reader, '_safe_get_cell', side_effect=mock_safe_get_cell):
            result = self.excel_reader._determine_insurance_period_pandas(mock_df)
            self.assertEqual(result, "1 год")
    
    def test_determine_insurance_period_pandas_n18_has_value(self):
        """Test pandas version with N18 having value"""
        mock_df = Mock()
        
        def mock_safe_get_cell(df, row, col):
            if row == 16 and col == 13:  # N17
                return None
            elif row == 17 and col == 13:  # N18
                return 'X'
            return None
        
        with patch.object(self.excel_reader, '_safe_get_cell', side_effect=mock_safe_get_cell):
            result = self.excel_reader._determine_insurance_period_pandas(mock_df)
            self.assertEqual(result, "на весь срок лизинга")
    
    def test_determine_insurance_period_pandas_both_empty(self):
        """Test pandas version with both cells empty"""
        mock_df = Mock()
        
        def mock_safe_get_cell(df, row, col):
            if row in [16, 17] and col == 13:  # N17, N18
                return None
            return None
        
        with patch.object(self.excel_reader, '_safe_get_cell', side_effect=mock_safe_get_cell):
            result = self.excel_reader._determine_insurance_period_pandas(mock_df)
            self.assertEqual(result, "")
    
    def test_determine_insurance_period_handles_whitespace(self):
        """Test that whitespace-only values are treated as empty"""
        mock_sheet = Mock()
        
        def mock_get_cell_value(sheet, cell_address):
            if cell_address == 'N17':
                return '   '  # Whitespace only
            elif cell_address == 'N18':
                return 'X'  # Has value
            return None
        
        with patch.object(self.excel_reader, '_get_cell_value', side_effect=mock_get_cell_value):
            result = self.excel_reader._determine_insurance_period_openpyxl(mock_sheet)
            self.assertEqual(result, "на весь срок лизинга")  # Should use N18
    
    def test_extract_data_openpyxl_uses_new_period_logic(self):
        """Test that _extract_data_openpyxl uses the new period determination"""
        mock_sheet = Mock()
        
        # Mock all the methods that _extract_data_openpyxl calls
        with patch.object(self.excel_reader, '_determine_insurance_type_openpyxl', return_value='КАСКО'), \
             patch.object(self.excel_reader, '_determine_insurance_period_openpyxl', return_value='1 год'), \
             patch.object(self.excel_reader, '_get_cell_value', return_value=None), \
             patch.object(self.excel_reader, '_find_leasing_object_info_openpyxl', return_value='Test vehicle'), \
             patch.object(self.excel_reader, '_find_dfa_number_openpyxl', return_value='DFA123'), \
             patch.object(self.excel_reader, '_find_branch_openpyxl', return_value='Test branch'), \
             patch('django.utils.timezone.now') as mock_now:
            
            from datetime import datetime, timedelta
            mock_now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            
            result = self.excel_reader._extract_data_openpyxl(mock_sheet)
            
            # Check that the new period logic is used
            self.assertEqual(result['insurance_period'], '1 год')
            self.assertIsNone(result['insurance_start_date'])
            self.assertIsNone(result['insurance_end_date'])
    
    def test_extract_data_pandas_uses_new_period_logic(self):
        """Test that _extract_data_pandas uses the new period determination"""
        mock_df = Mock()
        
        # Mock all the methods that _extract_data_pandas calls
        with patch.object(self.excel_reader, '_determine_insurance_type_pandas', return_value='КАСКО'), \
             patch.object(self.excel_reader, '_determine_insurance_period_pandas', return_value='на весь срок лизинга'), \
             patch.object(self.excel_reader, '_safe_get_cell', return_value=None), \
             patch.object(self.excel_reader, '_find_leasing_object_info_pandas', return_value='Test vehicle'), \
             patch.object(self.excel_reader, '_find_dfa_number_pandas', return_value='DFA123'), \
             patch.object(self.excel_reader, '_find_branch_pandas', return_value='Test branch'), \
             patch('django.utils.timezone.now') as mock_now:
            
            from datetime import datetime, timedelta
            mock_now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            
            result = self.excel_reader._extract_data_pandas(mock_df)
            
            # Check that the new period logic is used
            self.assertEqual(result['insurance_period'], 'на весь срок лизинга')
            self.assertIsNone(result['insurance_start_date'])
            self.assertIsNone(result['insurance_end_date'])


if __name__ == '__main__':
    unittest.main()