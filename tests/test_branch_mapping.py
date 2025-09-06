"""
Unit tests for branch mapping functionality
"""
import unittest
from unittest.mock import patch
from core.excel_utils import map_branch_name, BRANCH_MAPPING


class TestBranchMapping(unittest.TestCase):
    """Test cases for branch name mapping functionality"""
    
    def test_exact_branch_mapping(self):
        """Test exact branch name conversions"""
        # Test all defined mappings
        for full_name, expected_short_name in BRANCH_MAPPING.items():
            with self.subTest(full_name=full_name):
                result = map_branch_name(full_name)
                self.assertEqual(result, expected_short_name)
    
    def test_branch_mapping_with_whitespace(self):
        """Test branch mapping with extra whitespace"""
        test_cases = [
            ("  Казанский филиал  ", "Казань"),
            ("\tНижегородский филиал\n", "Нижний Новгород"),
            ("   Краснодарский филиал   ", "Краснодар"),
        ]
        
        for input_name, expected_output in test_cases:
            with self.subTest(input_name=repr(input_name)):
                result = map_branch_name(input_name)
                self.assertEqual(result, expected_output)
    
    def test_partial_branch_matching(self):
        """Test partial matching for branch names"""
        test_cases = [
            ("ООО Казанский филиал АО", "Казань"),
            ("Филиал Нижегородский", "Нижний Новгород"),
            ("Краснодарский", "Краснодар"),
        ]
        
        for input_name, expected_output in test_cases:
            with self.subTest(input_name=input_name):
                result = map_branch_name(input_name)
                self.assertEqual(result, expected_output)
    
    def test_case_insensitive_matching(self):
        """Test case insensitive matching"""
        test_cases = [
            ("казанский филиал", "Казань"),
            ("НИЖЕГОРОДСКИЙ ФИЛИАЛ", "Нижний Новгород"),
            ("КрАсНоДаРсКиЙ ФиЛиАл", "Краснодар"),
        ]
        
        for input_name, expected_output in test_cases:
            with self.subTest(input_name=input_name):
                result = map_branch_name(input_name)
                self.assertEqual(result, expected_output)
    
    def test_unknown_branch_fallback(self):
        """Test fallback behavior for unknown branches"""
        unknown_branches = [
            "Московский филиал",
            "Санкт-Петербургский филиал", 
            "Екатеринбургский филиал",
            "Неизвестный филиал",
            "Какой-то другой филиал"
        ]
        
        for branch_name in unknown_branches:
            with self.subTest(branch_name=branch_name):
                result = map_branch_name(branch_name)
                # Should return original name for unknown branches
                self.assertEqual(result, branch_name)
    
    def test_empty_and_none_inputs(self):
        """Test handling of empty and None inputs"""
        test_cases = [
            (None, "Филиал не указан"),
            ("", "Филиал не указан"),
            ("   ", "Филиал не указан"),  # Only whitespace
        ]
        
        for input_value, expected_output in test_cases:
            with self.subTest(input_value=repr(input_value)):
                result = map_branch_name(input_value)
                self.assertEqual(result, expected_output)
    
    def test_non_string_inputs(self):
        """Test handling of non-string inputs"""
        test_cases = [
            (123, "123"),
            ([], "[]"),
            ({}, "{}"),
            (True, "True"),
        ]
        
        for input_value, expected_output in test_cases:
            with self.subTest(input_value=input_value):
                result = map_branch_name(input_value)
                self.assertEqual(result, expected_output)
    
    @patch('core.excel_utils.logger')
    def test_logging_for_mapped_branches(self, mock_logger):
        """Test that successful mappings are logged at debug level"""
        map_branch_name("Казанский филиал")
        mock_logger.debug.assert_called_with("Mapped branch 'Казанский филиал' to 'Казань'")
    
    @patch('core.excel_utils.logger')
    def test_logging_for_partial_matches(self, mock_logger):
        """Test that partial matches are logged at debug level"""
        map_branch_name("ООО Казанский филиал")
        mock_logger.debug.assert_called_with(
            "Partially mapped branch 'ООО Казанский филиал' to 'Казань' via 'Казанский филиал'"
        )
    
    @patch('core.excel_utils.logger')
    def test_logging_for_unknown_branches(self, mock_logger):
        """Test that unknown branches are logged at info level"""
        unknown_branch = "Неизвестный филиал"
        map_branch_name(unknown_branch)
        mock_logger.info.assert_called_with(f"No mapping found for branch '{unknown_branch}', using original name")
    
    def test_branch_mapping_constants(self):
        """Test that BRANCH_MAPPING constant contains expected mappings"""
        expected_mappings = {
            "Казанский филиал": "Казань",
            "Нижегородский филиал": "Нижний Новгород",
            "Краснодарский филиал": "Краснодар"
        }
        
        self.assertEqual(BRANCH_MAPPING, expected_mappings)
        
        # Ensure all values are strings
        for key, value in BRANCH_MAPPING.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, str)
            self.assertTrue(len(key) > 0)
            self.assertTrue(len(value) > 0)


if __name__ == '__main__':
    unittest.main()