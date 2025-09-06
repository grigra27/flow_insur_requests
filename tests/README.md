# Insurance System Improvements - Test Suite

This directory contains comprehensive tests for the insurance system improvements implemented according to the requirements in `.kiro/specs/insurance-system-improvements/`.

## Test Structure

### Unit Tests

#### 1. Branch Mapping Tests (`test_branch_mapping.py`)
Tests the branch name mapping functionality that converts full branch names to short names.

**Coverage:**
- Exact branch name conversions for all defined mappings
- Whitespace handling and normalization
- Partial matching for branch names
- Case insensitive matching
- Fallback behavior for unknown branches
- Error handling for empty/None inputs
- Non-string input handling
- Logging verification for different scenarios

**Requirements Covered:** 2.1, 2.2, 2.3

#### 2. Insurance Type Detection Tests (`test_insurance_type_detection.py`)
Tests the logic for determining insurance type based on Excel cell values (D21/D22).

**Coverage:**
- КАСКО detection when D21 has value (openpyxl and pandas)
- Спецтехника detection when D21 empty and D22 has value
- "Другое" detection when both cells are empty
- Priority logic (D21 takes precedence over D22)
- Whitespace handling in cell values
- Error handling for cell access failures
- Integration with main Excel reading workflow

**Requirements Covered:** 4.1, 4.2, 4.3

#### 3. Date Extraction and Formatting Tests (`test_date_extraction.py`)
Tests date parsing from Excel cells and formatting for display.

**Coverage:**
- Multiple date format parsing (DD.MM.YYYY, YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY)
- Two-digit year handling
- DateTime and Date object handling
- Invalid date format handling
- Insurance period formatting
- InsuranceRequest model date property testing
- Integration with Excel data extraction

**Requirements Covered:** 6.1, 6.2, 6.4, 6.7

### Integration Tests

#### 4. Complete Workflow Tests (`test_integration_workflow.py`)
Tests the end-to-end workflow from Excel upload to email generation.

**Coverage:**
- Complete Excel upload workflow
- Email generation with updated data model
- Branch mapping integration
- Insurance type detection workflow
- Response deadline management
- Date fields integration
- Display name integration
- Template rendering with new display logic
- Error handling integration
- Performance testing for bulk operations

**Requirements Covered:** All requirements (1.1-6.7)

## Running Tests

### Run All Tests
```bash
python run_tests.py
```

### Run Individual Test Modules
```bash
# Branch mapping tests
python -m pytest tests/test_branch_mapping.py -v

# Insurance type detection tests  
python -m pytest tests/test_insurance_type_detection.py -v

# Date extraction tests
python -m pytest tests/test_date_extraction.py -v

# Integration workflow tests
python -m pytest tests/test_integration_workflow.py -v
```

### Run with Django Test Runner
```bash
# Run all tests
python manage.py test tests

# Run specific test class
python manage.py test tests.test_branch_mapping.TestBranchMapping

# Run specific test method
python manage.py test tests.test_branch_mapping.TestBranchMapping.test_exact_branch_mapping
```

## Test Coverage

The test suite provides comprehensive coverage for:

1. **Branch Mapping (Requirements 2.1-2.3)**
   - ✅ Exact mapping conversions
   - ✅ Partial matching logic
   - ✅ Fallback behavior
   - ✅ Error handling

2. **Insurance Type Detection (Requirements 4.1-4.3)**
   - ✅ D21/D22 cell logic for all three types
   - ✅ Both openpyxl and pandas code paths
   - ✅ Priority and edge cases

3. **Date Extraction (Requirements 6.1, 6.2, 6.4, 6.7)**
   - ✅ Multiple date format support
   - ✅ Date parsing and formatting
   - ✅ Insurance period property
   - ✅ Integration with Excel reading

4. **Complete Workflow (All Requirements)**
   - ✅ End-to-end Excel processing
   - ✅ Email generation with new data
   - ✅ Template rendering
   - ✅ Error handling
   - ✅ Performance considerations

## Test Data

Tests use mock data and Django test database to ensure:
- Isolation between test runs
- Predictable test outcomes
- No dependency on external files
- Fast execution

## Mocking Strategy

The tests use extensive mocking to:
- Isolate units under test
- Simulate Excel file reading without actual files
- Test error conditions safely
- Verify logging and side effects
- Ensure fast test execution

## Performance Tests

Integration tests include performance benchmarks for:
- Bulk request creation (100 requests < 5 seconds)
- Email generation (100 emails < 2 seconds)

## Continuous Integration

These tests are designed to run in CI/CD environments with:
- No external dependencies
- Deterministic outcomes
- Clear failure reporting
- Comprehensive coverage reporting

## Adding New Tests

When adding new functionality:

1. Add unit tests for individual functions/methods
2. Add integration tests for workflow changes
3. Update this README with new test descriptions
4. Ensure tests cover both success and failure scenarios
5. Add performance tests for operations that may impact system performance