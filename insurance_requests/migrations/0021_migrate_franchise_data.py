# Generated migration for migrating existing franchise data
# This migration converts existing has_franchise boolean values to the new franchise_type field
# Migration logic:
# - has_franchise = True  → franchise_type = 'with_franchise'
# - has_franchise = False → franchise_type = 'none'
# 
# Reverse migration logic:
# - franchise_type in ['with_franchise', 'both_variants'] → has_franchise = True
# - franchise_type = 'none' → has_franchise = False

from django.db import migrations
import logging

logger = logging.getLogger(__name__)


def migrate_franchise_data(apps, schema_editor):
    """
    Migrate existing has_franchise data to franchise_type field
    Logic: has_franchise = True → franchise_type = 'with_franchise'
           has_franchise = False → franchise_type = 'none'
    """
    InsuranceRequest = apps.get_model('insurance_requests', 'InsuranceRequest')
    
    total_records = InsuranceRequest.objects.count()
    migrated_count = 0
    error_count = 0
    
    logger.info(f"Starting franchise data migration for {total_records} records")
    
    try:
        # Update existing records in batches for better performance
        batch_size = 1000
        
        for request in InsuranceRequest.objects.all().iterator(chunk_size=batch_size):
            try:
                old_franchise_type = request.franchise_type
                
                if request.has_franchise:
                    request.franchise_type = 'with_franchise'
                else:
                    request.franchise_type = 'none'
                
                # Only save if the value actually changed
                if old_franchise_type != request.franchise_type:
                    request.save(update_fields=['franchise_type'])
                
                migrated_count += 1
                
                if migrated_count % 100 == 0:
                    logger.info(f"Migrated {migrated_count}/{total_records} records")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error migrating record ID {request.id}: {str(e)}")
                # Continue with other records instead of failing completely
                continue
        
        logger.info(f"Migration completed: {migrated_count} records migrated, {error_count} errors")
        
        if error_count > 0:
            logger.warning(f"Migration completed with {error_count} errors. Check logs for details.")
            
    except Exception as e:
        logger.error(f"Critical error during franchise data migration: {str(e)}")
        raise


def reverse_migrate_franchise_data(apps, schema_editor):
    """
    Reverse migration - update has_franchise based on franchise_type
    Logic: franchise_type in ['with_franchise', 'both_variants'] → has_franchise = True
           franchise_type = 'none' → has_franchise = False
    """
    InsuranceRequest = apps.get_model('insurance_requests', 'InsuranceRequest')
    
    total_records = InsuranceRequest.objects.count()
    migrated_count = 0
    error_count = 0
    
    logger.info(f"Starting reverse franchise data migration for {total_records} records")
    
    try:
        batch_size = 1000
        
        for request in InsuranceRequest.objects.all().iterator(chunk_size=batch_size):
            try:
                old_has_franchise = request.has_franchise
                new_has_franchise = request.franchise_type in ['with_franchise', 'both_variants']
                
                # Only save if the value actually changed
                if old_has_franchise != new_has_franchise:
                    request.has_franchise = new_has_franchise
                    request.save(update_fields=['has_franchise'])
                
                migrated_count += 1
                
                if migrated_count % 100 == 0:
                    logger.info(f"Reverse migrated {migrated_count}/{total_records} records")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error reverse migrating record ID {request.id}: {str(e)}")
                continue
        
        logger.info(f"Reverse migration completed: {migrated_count} records migrated, {error_count} errors")
        
        if error_count > 0:
            logger.warning(f"Reverse migration completed with {error_count} errors. Check logs for details.")
            
    except Exception as e:
        logger.error(f"Critical error during reverse franchise data migration: {str(e)}")
        raise


class Migration(migrations.Migration):

    dependencies = [
        ('insurance_requests', '0020_add_franchise_type_field'),
    ]

    operations = [
        migrations.RunPython(
            migrate_franchise_data,
            reverse_migrate_franchise_data,
        ),
    ]