"""
Django management command to clean up test data for InsuranceOffer model refactoring.

This command:
1. Deletes all existing InsuranceOffer records
2. Resets auto-increment counters
3. Prepares clean database for new structure

Requirements: 8.1, 8.2, 8.3
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from summaries.models import InsuranceOffer, InsuranceSummary
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up test data for InsuranceOffer model refactoring'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion of all InsuranceOffer records',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        """Execute the cleanup process"""
        
        # Count existing records
        offer_count = InsuranceOffer.objects.count()
        summary_count = InsuranceSummary.objects.count()
        
        self.stdout.write(
            self.style.WARNING(
                f'Found {offer_count} InsuranceOffer records and {summary_count} InsuranceSummary records'
            )
        )
        
        if offer_count == 0:
            self.stdout.write(
                self.style.SUCCESS('No InsuranceOffer records found. Database is already clean.')
            )
            return
        
        # Dry run mode
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE: The following would be deleted:')
            )
            self._show_records_to_delete()
            return
        
        # Require confirmation for actual deletion
        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    'This command will delete ALL InsuranceOffer records and reset auto-increment counters.\n'
                    'Use --confirm flag to proceed or --dry-run to see what would be deleted.'
                )
            )
            return
        
        # Perform cleanup
        try:
            with transaction.atomic():
                self._cleanup_data()
                self._reset_auto_increment()
                
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully cleaned up {offer_count} InsuranceOffer records and reset counters.'
                )
            )
            
            # Verify cleanup
            remaining_offers = InsuranceOffer.objects.count()
            if remaining_offers == 0:
                self.stdout.write(
                    self.style.SUCCESS('✓ Database is now clean and ready for new structure.')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Warning: {remaining_offers} records still remain!')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during cleanup: {str(e)}')
            )
            logger.error(f'Cleanup failed: {str(e)}')
            raise

    def _show_records_to_delete(self):
        """Show what records would be deleted in dry-run mode"""
        
        # Show InsuranceOffer records
        offers = InsuranceOffer.objects.select_related('summary__request').all()
        
        if offers.exists():
            self.stdout.write('\nInsuranceOffer records to be deleted:')
            for offer in offers:
                self.stdout.write(
                    f'  - ID: {offer.id}, Company: {offer.company_name}, '
                    f'Year: {offer.insurance_year}, Premium: {offer.insurance_premium}'
                )
        
        # Show InsuranceSummary records that would be affected
        summaries_with_offers = InsuranceSummary.objects.filter(offers__isnull=False).distinct()
        if summaries_with_offers.exists():
            self.stdout.write('\nInsuranceSummary records that will have their offers deleted:')
            for summary in summaries_with_offers:
                offer_count = summary.offers.count()
                self.stdout.write(
                    f'  - ID: {summary.id}, Request: {summary.request.get_display_name()}, '
                    f'Offers: {offer_count}'
                )

    def _cleanup_data(self):
        """Delete all InsuranceOffer records"""
        
        self.stdout.write('Deleting InsuranceOffer records...')
        
        # Get count before deletion for logging
        initial_count = InsuranceOffer.objects.count()
        
        # Delete all InsuranceOffer records
        # This will also update related InsuranceSummary records due to CASCADE
        deleted_count, deleted_details = InsuranceOffer.objects.all().delete()
        
        self.stdout.write(
            f'Deleted {deleted_count} records: {deleted_details}'
        )
        
        # Update InsuranceSummary records to reset counters
        self.stdout.write('Updating InsuranceSummary records...')
        updated_summaries = InsuranceSummary.objects.update(
            total_offers=0,
            best_premium=None,
            best_company=''
        )
        
        self.stdout.write(f'Updated {updated_summaries} InsuranceSummary records')
        
        logger.info(f'Cleaned up {initial_count} InsuranceOffer records')

    def _reset_auto_increment(self):
        """Reset auto-increment counters for InsuranceOffer table"""
        
        self.stdout.write('Resetting auto-increment counters...')
        
        with connection.cursor() as cursor:
            # Get the table name for InsuranceOffer
            table_name = InsuranceOffer._meta.db_table
            
            # Reset auto-increment counter to 1
            # This works for SQLite, PostgreSQL, and MySQL
            if connection.vendor == 'sqlite':
                # For SQLite, we need to reset the sqlite_sequence table
                cursor.execute(
                    "DELETE FROM sqlite_sequence WHERE name = %s",
                    [table_name]
                )
                self.stdout.write('Reset SQLite auto-increment sequence')
                
            elif connection.vendor == 'postgresql':
                # For PostgreSQL, reset the sequence
                sequence_name = f"{table_name}_id_seq"
                cursor.execute(f"ALTER SEQUENCE {sequence_name} RESTART WITH 1")
                self.stdout.write('Reset PostgreSQL sequence')
                
            elif connection.vendor == 'mysql':
                # For MySQL, reset auto-increment
                cursor.execute(f"ALTER TABLE {table_name} AUTO_INCREMENT = 1")
                self.stdout.write('Reset MySQL auto-increment')
                
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Auto-increment reset not implemented for {connection.vendor}'
                    )
                )
        
        logger.info('Reset auto-increment counters for InsuranceOffer table')

    def _verify_cleanup(self):
        """Verify that cleanup was successful"""
        
        remaining_offers = InsuranceOffer.objects.count()
        
        if remaining_offers == 0:
            self.stdout.write(
                self.style.SUCCESS('✓ Cleanup verification passed: No records remain')
            )
            return True
        else:
            self.stdout.write(
                self.style.ERROR(f'✗ Cleanup verification failed: {remaining_offers} records remain')
            )
            return False