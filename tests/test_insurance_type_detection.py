"""
Unit tests for insurance type detection functionality
"""
import unittest
from unittest.mock import Mock, MagicMock, patch
import pandas as pd
from core.excel_utils import ExcelReader


class TestInsuranceTypeDetection(unittest.TestCase):
    """Test cases for insurance type detection logic"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.excel_reader = ExcelReader("dummy_path.xlsx")
    
    def test_kasko_detection_openpyxl(self):
        """Test КАСКО detection with openpyxl (D21 has value)"""
        # Mock sheet with D21 having value, D22 empty
        mock_sheet = Mock()
        mock_sheet.__getitem__ = Mock()
        
        # Test cases where D21 has various values
        test_values = ["КАСКО", "да", "1", "любое значение", "x", " значение с пробелами "]
        
        for d21_value in test_values:
            with self.subTest(d21_value=d21_value):
                # Mock D21 cell with value, D22 cell empty
                mock_sheet.__getitem__.side_effect = lambda cell: (
                    Mock(value=d21_value) if cell == 'D21' else Mock(value=None)
                )
                
                result = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
                self.assertEqual(result, 'КАСКО')
    
    def test_specialtech_detection_openpyxl(self):
        """Test спецтехника detection with openpyxl (D21 empty, D22 has value)"""
        mock_sheet = Mock()
        mock_sheet.__getitem__ = Mock()
        
        # Test cases where D22 has various values and D21 is empty
        test_values = ["спецтехника", "да", "1", "любое значение", "x", " значение с пробелами "]
        
        for d22_value in test_values:
            with self.subTest(d22_value=d22_value):
                # Mock D21 cell empty, D22 cell with value
                mock_sheet.__getitem__.side_effect = lambda cell: (
                    Mock(value=None) if cell == 'D21' else Mock(value=d22_value)
                )
                
                result = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
                self.assertEqual(result, 'страхование спецтехники')
    
    def test_other_detection_openpyxl(self):
        """Test другое detection with openpyxl (both D21 and D22 empty)"""
        mock_sheet = Mock()
        mock_sheet.__getitem__ = Mock()
        
        # Test cases where both cells are empty
        empty_values = [None, "", "   ", "  \t  \n  "]
        
        for d21_value in empty_values:
            for d22_value in empty_values:
                with self.subTest(d21_value=repr(d21_value), d22_value=repr(d22_value)):
                    mock_sheet.__getitem__.side_effect = lambda cell: (
                        Mock(value=d21_value) if cell == 'D21' else Mock(value=d22_value)
                    )
                    
                    result = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
                    self.assertEqual(result, 'другое')
    
    def test_kasko_priority_openpyxl(self):
        """Test that D21 (КАСКО) has priority over D22 with openpyxl"""
        mock_sheet = Mock()
        mock_sheet.__getitem__ = Mock()
        
        # Both cells have values - D21 should take priority
        mock_sheet.__getitem__.side_effect = lambda cell: (
            Mock(value="КАСКО") if cell == 'D21' else Mock(value="спецтехника")
        )
        
        result = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
        self.assertEqual(result, 'КАСКО')
    
    def test_kasko_detection_pandas(self):
        """Test КАСКО detection with pandas (D21 has value)"""
        # Create mock DataFrame
        mock_df = Mock()
        
        # Test cases where D21 (row 20, col 3) has various values
        test_values = ["КАСКО", "да", "1", "любое значение", "x", " значение с пробелами "]
        
        for d21_value in test_values:
            with self.subTest(d21_value=d21_value):
                # Mock iloc to return D21 value and D22 None
                mock_df.iloc = Mock()
                mock_df.iloc.__getitem__ = Mock(side_effect=lambda key: (
                    d21_value if key == (20, 3) else None
                ))
                
                with patch.object(self.excel_reader, '_safe_get_cell') as mock_safe_get:
                    mock_safe_get.side_effect = lambda df, row, col: (
                        d21_value if (row, col) == (20, 3) else None
                    )
                    
                    result = self.excel_reader._determine_insurance_type_pandas(mock_df)
                    self.assertEqual(result, 'КАСКО')
    
    def test_specialtech_detection_pandas(self):
        """Test спецтехника detection with pandas (D21 empty, D22 has value)"""
        mock_df = Mock()
        
        # Test cases where D22 (row 21, col 3) has various values and D21 is empty
        test_values = ["спецтехника", "да", "1", "любое значение", "x", " значение с пробелами "]
        
        for d22_value in test_values:
            with self.subTest(d22_value=d22_value):
                with patch.object(self.excel_reader, '_safe_get_cell') as mock_safe_get:
                    mock_safe_get.side_effect = lambda df, row, col: (
                        None if (row, col) == (20, 3) else d22_value if (row, col) == (21, 3) else None
                    )
                    
                    result = self.excel_reader._determine_insurance_type_pandas(mock_df)
                    self.assertEqual(result, 'страхование спецтехники')
    
    def test_other_detection_pandas(self):
        """Test другое detection with pandas (both D21 and D22 empty)"""
        mock_df = Mock()
        
        # Test cases where both cells are empty
        empty_values = [None, "", "   ", "  \t  \n  "]
        
        for d21_value in empty_values:
            for d22_value in empty_values:
                with self.subTest(d21_value=repr(d21_value), d22_value=repr(d22_value)):
                    with patch.object(self.excel_reader, '_safe_get_cell') as mock_safe_get:
                        mock_safe_get.side_effect = lambda df, row, col: (
                            d21_value if (row, col) == (20, 3) else 
                            d22_value if (row, col) == (21, 3) else None
                        )
                        
                        result = self.excel_reader._determine_insurance_type_pandas(mock_df)
                        self.assertEqual(result, 'другое')
    
    def test_kasko_priority_pandas(self):
        """Test that D21 (КАСКО) has priority over D22 with pandas"""
        mock_df = Mock()
        
        # Both cells have values - D21 should take priority
        with patch.object(self.excel_reader, '_safe_get_cell') as mock_safe_get:
            mock_safe_get.side_effect = lambda df, row, col: (
                "КАСКО" if (row, col) == (20, 3) else 
                "спецтехника" if (row, col) == (21, 3) else None
            )
            
            result = self.excel_reader._determine_insurance_type_pandas(mock_df)
            self.assertEqual(result, 'КАСКО')
    
    def test_cell_access_error_handling_openpyxl(self):
        """Test error handling when cell access fails with openpyxl"""
        mock_sheet = Mock()
        mock_sheet.__getitem__.side_effect = Exception("Cell access error")
        
        with patch.object(self.excel_reader, '_get_cell_value') as mock_get_cell:
            mock_get_cell.return_value = None
            
            result = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
            self.assertEqual(result, 'другое')
    
    def test_cell_access_error_handling_pandas(self):
        """Test error handling when cell access fails with pandas"""
        mock_df = Mock()
        
        with patch.object(self.excel_reader, '_safe_get_cell') as mock_safe_get:
            mock_safe_get.return_value = None
            
            result = self.excel_reader._determine_insurance_type_pandas(mock_df)
            self.assertEqual(result, 'другое')
    
    def test_integration_with_read_insurance_request(self):
        """Test insurance type detection integration with main read method"""
        # Test that the insurance type detection is properly integrated
        with patch('core.excel_utils.load_workbook') as mock_load_wb:
            with patch('pandas.read_excel') as mock_read_excel:
                # Mock successful openpyxl path
                mock_workbook = Mock()
                mock_sheet = Mock()
                mock_workbook.active = mock_sheet
                mock_load_wb.return_value = mock_workbook
                
                # Mock D21 with КАСКО value
                mock_sheet.__getitem__ = Mock(side_effect=lambda cell: (
                    Mock(value="КАСКО") if cell == 'D21' else Mock(value=None)
                ))
                
                with patch.object(self.excel_reader, '_get_cell_value') as mock_get_cell:
                    mock_get_cell.side_effect = lambda sheet, cell: (
                        "КАСКО" if cell == 'D21' else 
                        None if cell == 'D22' else
                        "test_value"  # Default for other cells
                    )
                    
                    with patch.object(self.excel_reader, '_find_leasing_object_info_openpyxl'):
                        with patch.object(self.excel_reader, '_find_dfa_number_openpyxl'):
                            with patch.object(self.excel_reader, '_find_branch_openpyxl'):
                                with patch.object(self.excel_reader, '_parse_date'):
                                    result = self.excel_reader.read_insurance_request()
                                    self.assertEqual(result['insurance_type'], 'КАСКО')
    
    def test_whitespace_handling(self):
        """Test that whitespace in cell values is properly handled"""
        mock_sheet = Mock()
        mock_sheet.__getitem__ = Mock()
        
        # Test values with various whitespace
        whitespace_values = [
            ("  КАСКО  ", 'КАСКО'),
            ("\tспецтехника\n", 'страхование спецтехники'),
            ("   ", 'другое'),  # Only whitespace should be treated as empty
        ]
        
        for cell_value, expected_type in whitespace_values:
            with self.subTest(cell_value=repr(cell_value)):
                mock_sheet.__getitem__.side_effect = lambda cell: (
                    Mock(value=cell_value) if cell == 'D21' else Mock(value=None)
                    if expected_type == 'КАСКО' else
                    Mock(value=None) if cell == 'D21' else Mock(value=cell_value)
                    if expected_type == 'страхование спецтехники' else
                    Mock(value=cell_value) if cell in ['D21', 'D22'] else Mock(value=None)
                )
                
                result = self.excel_reader._determine_insurance_type_openpyxl(mock_sheet)
                self.assertEqual(result, expected_type)


if __name__ == '__main__':
    unittest.main()