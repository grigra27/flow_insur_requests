# Generated migration for summaries performance optimizations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('summaries', '0001_initial'),
    ]

    operations = [
        # Add indexes for frequently queried fields in InsuranceSummary
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_summary_status ON summaries_insurancesummary(status);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_summary_status;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_summary_created_at ON summaries_insurancesummary(created_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_summary_created_at;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_summary_request ON summaries_insurancesummary(request_id);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_summary_request;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_summary_best_premium ON summaries_insurancesummary(best_premium);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_summary_best_premium;"
        ),
        
        # Add indexes for InsuranceOffer
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_offer_summary ON summaries_insuranceoffer(summary_id);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_offer_summary;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_offer_company_name ON summaries_insuranceoffer(company_name);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_offer_company_name;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_offer_premium ON summaries_insuranceoffer(insurance_premium);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_offer_premium;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_offer_received_at ON summaries_insuranceoffer(received_at);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_offer_received_at;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_offer_is_valid ON summaries_insuranceoffer(is_valid);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_offer_is_valid;"
        ),
        
        # Add composite indexes for common query patterns
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_offer_summary_premium ON summaries_insuranceoffer(summary_id, insurance_premium);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_offer_summary_premium;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_insurance_offer_valid_premium ON summaries_insuranceoffer(is_valid, insurance_premium);",
            reverse_sql="DROP INDEX IF EXISTS idx_insurance_offer_valid_premium;"
        ),
        
        # Add indexes for SummaryTemplate
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_summary_template_is_active ON summaries_summarytemplate(is_active);",
            reverse_sql="DROP INDEX IF EXISTS idx_summary_template_is_active;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_summary_template_is_default ON summaries_summarytemplate(is_default);",
            reverse_sql="DROP INDEX IF EXISTS idx_summary_template_is_default;"
        ),
    ]