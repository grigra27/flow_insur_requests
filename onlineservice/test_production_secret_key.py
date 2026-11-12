import os
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.check_production_secret_key import validate_secret_key


VALID_KEY = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_production_secret_key.py'


class ProductionSecretKeyTests(unittest.TestCase):
    def test_accepts_long_diverse_key(self):
        validate_secret_key(VALID_KEY)

    def test_rejects_missing_or_empty_key(self):
        for value in (None, ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_secret_key(value)

    def test_rejects_short_key(self):
        with self.assertRaises(ValueError):
            validate_secret_key(VALID_KEY[:49])

    def test_rejects_repeated_key(self):
        with self.assertRaises(ValueError):
            validate_secret_key('abcd' * 30)

    def test_rejects_development_prefix_even_with_long_diverse_key(self):
        with self.assertRaises(ValueError):
            validate_secret_key('django-insecure-' + VALID_KEY)

    def test_rejects_line_breaks_in_environment_file_value(self):
        for ending in ('\nINJECTED=True', '\rINJECTED=True'):
            with self.subTest(ending=repr(ending)), self.assertRaises(ValueError):
                validate_secret_key(VALID_KEY + ending)

    def test_cli_rejects_key_without_disclosing_it(self):
        value = 'django-insecure-' + VALID_KEY
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                                text=True, env={**os.environ, 'TIMEWEB_SECRET_KEY': value})
        self.assertEqual(result.returncode, 1)
        self.assertIn('Production SECRET_KEY', result.stderr)
        self.assertNotIn(value, result.stdout + result.stderr)
        self.assertEqual(result.stdout, '')

    def test_cli_accepts_key_without_printing_it(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                                text=True, env={**os.environ, 'TIMEWEB_SECRET_KEY': VALID_KEY})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout + result.stderr, '')
