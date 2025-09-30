"""
Integration test to verify that Excel processing uses the new period determination logic
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
from core.excel_utils import ExcelReader


class TestPeriodIntegration(unittest.TestCase):
    """Integration test for the new period determination logic"""
    
    def test_excel_reader_integration_with_new_period_logic(self):
        """Test that ExcelReader.read_insurance_request uses new period logic"""
        excel_reader = ExcelReader("dummy_path.xlsx")
        
        # Mock the file loading and sheet access
        mock_workbook = Mock()
        mock_sheet = Mock()
        mock_workbook.active = mock_sheet
        
        # Mock the cell values to simulate N17 having a value
        def mock_get_cell_value(sheet, cell_address):
            if cell_address == 'N17':
                return 'X'  # Has value -> should return "1 год"
            elif cell_address == 'N18':
                return None  # Empty
            elif cell_address == 'D7':
                return 'Test Client'
            elif cell_address == 'D9':
                return '1234567890'
            elif cell_address in ['D21', 'D22', 'D23']:
                return 'X' if cell_address == 'D21' else None  # КАСКО
            else:
                return None
        
        with patch('openpyxl.load_workbook', return_value=mock_workbook), \
             patch.object(excel_reader, '_get_cell_value', side_effect=mock_get_cell_value), \
             patch.object(excel_reader, '_find_leasing_object_info_openpyxl', return_value='Test vehicle'), \
             patch.object(excel_reader, '_find_dfa_number_openpyxl', return_value='DFA123'), \
             patch.object(excel_reader, '_find_branch_openpyxl', return_value='Test branch'), \
             patch('django.utils.timezone.now') as mock_now:
            
            from datetime import datetime, timedelta
            mock_now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            
            # Call the method directly to avoid file system issues
            result = excel_reader._extract_data_openpyxl(mock_sheet)
            
            # Verify that the new period logic is used
            self.assertEqual(result['insurance_period'], '1 год')
            self.assertIsNone(result['insurance_start_date'])
            self.assertIsNone(result['insurance_end_date'])
            self.assertEqual(result['client_name'], 'Test Client')
            self.assertEqual(result['insurance_type'], 'КАСКО')
    
    def test_excel_reader_integration_with_n18_period(self):
        """Test that ExcelReader uses N18 when N17 is empty"""
        excel_reader = ExcelReader("dummy_path.xlsx")
        
        # Mock the file loading and sheet access
        mock_workbook = Mock()
        mock_sheet = Mock()
        mock_workbook.active = mock_sheet
        
        # Mock the cell values to simulate N18 having a value
        def mock_get_cell_value(sheet, cell_address):
            if cell_address == 'N17':
                return None  # Empty
            elif cell_address == 'N18':
                return 'X'  # Has value -> should return "на весь срок лизинга"
            elif cell_address == 'D7':
                return 'Test Client'
            elif cell_address == 'D9':
                return '1234567890'
            elif cell_address in ['D21', 'D22', 'D23']:
                return 'X' if cell_address == 'D21' else None  # КАСКО
            else:
                return None
        
        with patch('openpyxl.load_workbook', return_value=mock_workbook), \
             patch.object(excel_reader, '_get_cell_value', side_effect=mock_get_cell_value), \
             patch.object(excel_reader, '_find_leasing_object_info_openpyxl', return_value='Test vehicle'), \
             patch.object(excel_reader, '_find_dfa_number_openpyxl', return_value='DFA123'), \
             patch.object(excel_reader, '_find_branch_openpyxl', return_value='Test branch'), \
             patch('django.utils.timezone.now') as mock_now:
            
            from datetime import datetime, timedelta
            mock_now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            
            # Call the method directly to avoid file system issues
            result = excel_reader._extract_data_openpyxl(mock_sheet)
            
            # Verify that the new period logic is used
            self.assertEqual(result['insurance_period'], 'на весь срок лизинга')
            self.assertIsNone(result['insurance_start_date'])
            self.assertIsNone(result['insurance_end_date'])
    
    def test_excel_reader_integration_with_pandas_fallback(self):
        """Test that pandas fallback also uses new period logic"""
        excel_reader = ExcelReader("dummy_path.xls")
        
        # Mock pandas DataFrame
        mock_df = Mock()
        
        def mock_safe_get_cell(df, row, col):
            if row == 16 and col == 13:  # N17
                return 'X'  # Has value -> should return "1 год"
            elif row == 17 and col == 13:  # N18
                return None  # Empty
            elif row == 6 and col == 3:  # D7 - client name
                return 'Test Client'
            elif row == 8 and col == 3:  # D9 - INN
                return '1234567890'
            elif row == 20 and col == 3:  # D21 - КАСКО
                return 'X'
            elif row in [21, 22] and col == 3:  # D22, D23
                return None
            else:
                return None
        
        with patch.object(excel_reader, '_safe_get_cell', side_effect=mock_safe_get_cell), \
             patch.object(excel_reader, '_find_leasing_object_info_pandas', return_value='Test vehicle'), \
             patch.object(excel_reader, '_find_dfa_number_pandas', return_value='DFA123'), \
             patch.object(excel_reader, '_find_branch_pandas', return_value='Test branch'), \
             patch('django.utils.timezone.now') as mock_now:
            
            from datetime import datetime, timedelta
            mock_now.return_value = datetime(2024, 1, 1, 12, 0, 0)
            
            # Call the method directly to avoid file system issues
            result = excel_reader._extract_data_pandas(mock_df)
            
            # Verify that the new period logic is used in pandas fallback
            self.assertEqual(result['insurance_period'], '1 год')
            self.assertIsNone(result['insurance_start_date'])
            self.assertIsNone(result['insurance_end_date'])


if __name__ == '__main__':
    unittest.main()