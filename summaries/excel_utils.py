"""
Utility functions for Excel export functionality
"""
import logging
from pathlib import Path
from django.conf import settings

logger = logging.getLogger('summaries.excel_export')


def validate_excel_template():
    """
    Validate that the Excel template file exists and is accessible
    
    Returns:
        bool: True if template is valid and accessible, False otherwise
    """
    template_path = Path(settings.SUMMARY_TEMPLATE_PATH)
    
    if not template_path.exists():
        logger.error(f"Excel template not found at: {template_path}")
        return False
    
    if not template_path.is_file():
        logger.error(f"Excel template path is not a file: {template_path}")
        return False
    
    try:
        # Try to read the file to ensure it's accessible
        with open(template_path, 'rb') as f:
            f.read(1)  # Read just one byte to test accessibility
        logger.info(f"Excel template validated successfully: {template_path}")
        return True
    except Exception as e:
        logger.error(f"Cannot access Excel template: {e}")
        return False


def get_template_path():
    """
    Get the path to the Excel template file
    
    Returns:
        Path: Path to the template file
    """
    return Path(settings.SUMMARY_TEMPLATE_PATH)