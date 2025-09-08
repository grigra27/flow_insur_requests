# Generated migration for database performance optimizations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insurance_requests', '0011_add_casco_ce_field'),
    ]

    operations = [
        # Add indexes for frequently queried fields in InsuranceRequest
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_request_status ON insurance_requests_insurancerequest(status);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_request_status;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_request_created_at ON insurance_requests_insurancerequest(created_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_request_created_at;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_request_created_by ON insurance_requests_insurancerequest(created_by_id);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_request_created_by;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_request_insurance_type ON insurance_requests_insurancerequest(insurance_type);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_request_insurance_type;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_request_branch ON insurance_requests_insurancerequest(branch);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_request_branch;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_request_dfa_number ON insurance_requests_insurancerequest(dfa_number);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_request_dfa_number;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_request_response_deadline ON insurance_requests_insurancerequest(response_deadline);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_request_response_deadline;"
        ),
        
        # Add composite indexes for common query patterns
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_request_status_created_at ON insurance_requests_insurancerequest(status, created_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_request_status_created_at;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_request_created_by_status ON insurance_requests_insurancerequest(created_by_id, status);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_request_created_by_status;"
        ),
        
        # Add indexes for RequestAttachment
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_request_attachment_request ON insurance_requests_requestattachment(request_id);",
            reverse_sql="DROP INDEX IF EXISTS idx_request_attachment_request;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_request_attachment_uploaded_at ON insurance_requests_requestattachment(uploaded_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_request_attachment_uploaded_at;"
        ),
        
        # Add indexes for InsuranceResponse
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_response_request ON insurance_requests_insuranceresponse(request_id);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_response_request;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_response_received_at ON insurance_requests_insuranceresponse(received_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_response_received_at;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_response_company_name ON insurance_requests_insuranceresponse(company_name);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_response_company_name;"
        ),
    ]