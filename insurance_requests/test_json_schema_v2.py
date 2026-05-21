"""Tests for the canonical JSON Schema v2 contract.

The schema lives in docs/insurance_request_format_package/insurance_request_schema_v2.json
and is the contract between the V2 parser, the InsuranceRequest DB row and the
upcoming PDF/JSON generator (stage 5+). This test pins down two invariants:

1. The schema itself is a valid Draft 2020-12 JSON Schema.
2. Every checked-in example payload in that directory validates against it.
"""
import json
from pathlib import Path

import jsonschema
from django.test import TestCase

PACKAGE_DIR = Path(__file__).resolve().parent.parent / 'docs' / 'insurance_request_format_package'
SCHEMA_PATH = PACKAGE_DIR / 'insurance_request_schema_v2.json'


class InsuranceRequestSchemaV2Test(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))

    def test_schema_is_valid_draft_2020_12(self):
        # Raises SchemaError if anything is wrong with the schema itself.
        jsonschema.Draft202012Validator.check_schema(self.schema)

    def test_schema_version_constant_is_v2(self):
        self.assertEqual(
            self.schema['properties']['schema_version']['const'],
            'alliance.insurance_request.v2',
        )

    def test_schema_uses_singular_insured_object(self):
        # The whole splitting principle hangs on this: one document = one object.
        self.assertIn('insured_object', self.schema['properties'])
        self.assertNotIn('insured_objects', self.schema['properties'])

    def test_schema_drops_v1_fields_that_have_no_source(self):
        # See docs/improvement_plans/json_schema_v2.md «Удаляем из схемы».
        insured_object = self.schema['$defs']['insured_object']['properties']
        for absent in ('vin', 'serial_number', 'quantity'):
            self.assertNotIn(absent, insured_object, f'{absent} must not be in v2')

        coverage_terms = self.schema['properties']['insurance']['properties']['coverage_terms']['properties']
        self.assertNotIn('indemnity_basis', coverage_terms)

        lease = self.schema['properties']['lease']['properties']
        for absent in ('contract_start_date', 'contract_end_date'):
            self.assertNotIn(absent, lease)

    def test_examples_all_validate_against_schema(self):
        examples = sorted(PACKAGE_DIR.glob('example_*.json'))
        self.assertGreater(len(examples), 0, 'expected at least one example payload')
        for example_path in examples:
            with self.subTest(example=example_path.name):
                payload = json.loads(example_path.read_text(encoding='utf-8'))
                # validate() raises on failure with a useful message.
                jsonschema.validate(payload, self.schema)

    def test_batch_examples_share_one_batch_id(self):
        # The two 18022 examples represent siblings from the same upload —
        # they must share batch_id and have consistent item_count.
        first = json.loads((PACKAGE_DIR / 'example_insurance_request_18022_batch_item_1.json').read_text(encoding='utf-8'))
        second = json.loads((PACKAGE_DIR / 'example_insurance_request_18022_batch_item_2.json').read_text(encoding='utf-8'))
        self.assertEqual(first['request']['batch']['batch_id'], second['request']['batch']['batch_id'])
        self.assertEqual(first['request']['batch']['item_count'], 2)
        self.assertEqual(second['request']['batch']['item_count'], 2)
        self.assertEqual({first['request']['batch']['item_no'], second['request']['batch']['item_no']}, {1, 2})
