"""
Management command for log maintenance operations
"""
from django.core.management.base import BaseCommand, CommandError
from core.log_management import LogManager


class Command(BaseCommand):
    help = 'Perform log maintenance operations (rotation, compression, cleanup)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            choices=['rotate', 'compress', 'cleanup', 'archive', 'stats', 'maintenance'],
            default='maintenance',
            help='Maintenance action to perform (default: maintenance - does all)'
        )
        
        parser.add_argument(
            '--days',
            type=int,
            help='Number of days for age-based operations'
        )
        
        parser.add_argument(
            '--size',
            type=int,
            help='Maximum file size in MB for rotation'
        )
        
        parser.add_argument(
            '--archive-dir',
            type=str,
            help='Directory for archiving logs'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually doing it'
        )
    
    def handle(self, *args, **options):
        action = options['action']
        days = options['days']
        size = options['size']
        archive_dir = options['archive_dir']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        try:
            manager = LogManager()
            
            if action == 'stats':
                self.show_log_statistics(manager)
            elif action == 'rotate':
                self.rotate_logs(manager, size, dry_run)
            elif action == 'compress':
                self.compress_logs(manager, days, dry_run)
            elif action == 'cleanup':
                self.cleanup_logs(manager, days, dry_run)
            elif action == 'archive':
                self.archive_logs(manager, archive_dir, days, dry_run)
            elif action == 'maintenance':
                self.perform_maintenance(manager, dry_run)
            
        except Exception as e:
            raise CommandError(f'Error performing log maintenance: {e}')
    
    def show_log_statistics(self, manager):
        """Display log file statistics"""
        stats = manager.get_log_file_stats()
        
        self.stdout.write(self.style.SUCCESS('\n=== LOG FILE STATISTICS ==='))
        self.stdout.write(f"Total files: {stats['total_files']}")
        self.stdout.write(f"Total size: {stats['total_size'] / 1024 / 1024:.2f} MB")
        self.stdout.write(f"Compressed files: {stats['compressed_files']}")
        self.stdout.write(f"Uncompressed files: {stats['uncompressed_files']}")
        
        if stats['oldest_file']:
            self.stdout.write(f"Oldest file: {stats['oldest_file']['name']} ({stats['oldest_file']['date']})")
        
        if stats['newest_file']:
            self.stdout.write(f"Newest file: {stats['newest_file']['name']} ({stats['newest_file']['date']})")
        
        if stats['largest_file']:
            size_mb = stats['largest_file']['size'] / 1024 / 1024
            self.stdout.write(f"Largest file: {stats['largest_file']['name']} ({size_mb:.2f} MB)")
        
        if stats['files_by_type']:
            self.stdout.write('\nFiles by type:')
            for log_type, type_stats in stats['files_by_type'].items():
                size_mb = type_stats['size'] / 1024 / 1024
                self.stdout.write(f"  {log_type}: {type_stats['count']} files, {size_mb:.2f} MB")
    
    def rotate_logs(self, manager, size, dry_run):
        """Rotate log files"""
        max_size = (size * 1024 * 1024) if size else None
        
        self.stdout.write(self.style.SUCCESS('Rotating log files...'))
        
        if dry_run:
            self.stdout.write('Would rotate files exceeding size limit')
            return
        
        active_logs = ['django.log', 'performance.log', 'security.log', 
                      'file_uploads.log', 'errors.log', 'queries.log']
        
        rotated_count = 0
        for log_name in active_logs:
            log_path = manager.log_dir / log_name
            if manager.rotate_log_file(log_path, max_size):
                rotated_count += 1
                self.stdout.write(f"Rotated: {log_name}")
        
        self.stdout.write(f"Rotated {rotated_count} log files")
    
    def compress_logs(self, manager, days, dry_run):
        """Compress old log files"""
        self.stdout.write(self.style.SUCCESS('Compressing old log files...'))
        
        if dry_run:
            days_old = days or manager.compress_after_days
            self.stdout.write(f'Would compress files older than {days_old} days')
            return
        
        compressed_count = manager.compress_old_logs(days)
        self.stdout.write(f"Compressed {compressed_count} log files")
    
    def cleanup_logs(self, manager, days, dry_run):
        """Clean up very old log files"""
        self.stdout.write(self.style.SUCCESS('Cleaning up old log files...'))
        
        if dry_run:
            days_old = days or manager.max_age_days
            self.stdout.write(f'Would remove files older than {days_old} days')
            return
        
        removed_count = manager.cleanup_old_logs(days)
        self.stdout.write(f"Removed {removed_count} old log files")
    
    def archive_logs(self, manager, archive_dir, days, dry_run):
        """Archive log files"""
        self.stdout.write(self.style.SUCCESS('Archiving log files...'))
        
        if dry_run:
            days_old = days or 7
            archive_path = archive_dir or (manager.log_dir / 'archive')
            self.stdout.write(f'Would archive files older than {days_old} days to {archive_path}')
            return
        
        archived_count = manager.archive_logs(archive_dir, days)
        self.stdout.write(f"Archived {archived_count} log files")
    
    def perform_maintenance(self, manager, dry_run):
        """Perform complete log maintenance"""
        self.stdout.write(self.style.SUCCESS('Performing complete log maintenance...'))
        
        if dry_run:
            self.stdout.write('Would perform:')
            self.stdout.write('  - Rotate large log files')
            self.stdout.write('  - Compress files older than 7 days')
            self.stdout.write('  - Remove files older than 30 days')
            return
        
        stats = manager.perform_maintenance()
        
        self.stdout.write(f"Maintenance completed:")
        self.stdout.write(f"  Rotated files: {stats['rotated_files']}")
        self.stdout.write(f"  Compressed files: {stats['compressed_files']}")
        self.stdout.write(f"  Removed files: {stats['removed_files']}")
        
        if stats['errors']:
            self.stdout.write(self.style.ERROR('Errors encountered:'))
            for error in stats['errors']:
                self.stdout.write(f"  {error}")
        else:
            self.stdout.write(self.style.SUCCESS('No errors encountered'))