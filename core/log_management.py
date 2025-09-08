"""
Log management utilities for rotation, cleanup, and archiving
"""
import os
import gzip
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)


class LogManager:
    """Manage log files - rotation, compression, and cleanup"""
    
    def __init__(self, log_dir=None):
        self.log_dir = Path(log_dir or settings.BASE_DIR / 'logs')
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.max_age_days = 30  # Keep logs for 30 days
        self.compress_after_days = 7  # Compress logs older than 7 days
    
    def rotate_log_file(self, log_file_path, max_size=None):
        """Rotate a log file if it exceeds the maximum size"""
        log_file = Path(log_file_path)
        if not log_file.exists():
            return False
        
        max_size = max_size or self.max_file_size
        
        if log_file.stat().st_size > max_size:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            rotated_name = f"{log_file.stem}_{timestamp}.log"
            rotated_path = log_file.parent / rotated_name
            
            try:
                # Move current log to rotated name
                shutil.move(str(log_file), str(rotated_path))
                
                # Create new empty log file
                log_file.touch()
                
                logger.info(f"Rotated log file: {log_file} -> {rotated_path}")
                return True
            
            except Exception as e:
                logger.error(f"Error rotating log file {log_file}: {e}")
                return False
        
        return False
    
    def compress_old_logs(self, days_old=None):
        """Compress log files older than specified days"""
        days_old = days_old or self.compress_after_days
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        compressed_count = 0
        
        for log_file in self.log_dir.glob('*.log'):
            try:
                # Skip current active log files
                if log_file.name in ['django.log', 'performance.log', 'security.log', 
                                   'file_uploads.log', 'errors.log', 'queries.log']:
                    continue
                
                # Check file age
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_time < cutoff_date:
                    # Compress the file
                    compressed_path = log_file.with_suffix('.log.gz')
                    
                    with open(log_file, 'rb') as f_in:
                        with gzip.open(compressed_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    
                    # Remove original file
                    log_file.unlink()
                    
                    logger.info(f"Compressed log file: {log_file} -> {compressed_path}")
                    compressed_count += 1
            
            except Exception as e:
                logger.error(f"Error compressing log file {log_file}: {e}")
        
        return compressed_count
    
    def cleanup_old_logs(self, days_old=None):
        """Remove log files older than specified days"""
        days_old = days_old or self.max_age_days
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        removed_count = 0
        
        # Clean up both .log and .log.gz files
        for pattern in ['*.log', '*.log.gz']:
            for log_file in self.log_dir.glob(pattern):
                try:
                    # Skip current active log files
                    if log_file.name in ['django.log', 'performance.log', 'security.log', 
                                       'file_uploads.log', 'errors.log', 'queries.log']:
                        continue
                    
                    # Check file age
                    file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if file_time < cutoff_date:
                        log_file.unlink()
                        logger.info(f"Removed old log file: {log_file}")
                        removed_count += 1
                
                except Exception as e:
                    logger.error(f"Error removing log file {log_file}: {e}")
        
        return removed_count
    
    def get_log_file_stats(self):
        """Get statistics about log files"""
        stats = {
            'total_files': 0,
            'total_size': 0,
            'compressed_files': 0,
            'uncompressed_files': 0,
            'oldest_file': None,
            'newest_file': None,
            'largest_file': None,
            'files_by_type': {}
        }
        
        oldest_time = None
        newest_time = None
        largest_size = 0
        
        for log_file in self.log_dir.glob('*'):
            if log_file.is_file() and (log_file.suffix == '.log' or log_file.name.endswith('.log.gz')):
                stats['total_files'] += 1
                file_size = log_file.stat().st_size
                stats['total_size'] += file_size
                
                # Track file types
                if log_file.name.endswith('.log.gz'):
                    stats['compressed_files'] += 1
                    file_type = 'compressed'
                else:
                    stats['uncompressed_files'] += 1
                    file_type = 'uncompressed'
                
                # Track by log type
                log_type = log_file.stem.split('_')[0]  # Get base name before timestamp
                if log_type not in stats['files_by_type']:
                    stats['files_by_type'][log_type] = {'count': 0, 'size': 0}
                stats['files_by_type'][log_type]['count'] += 1
                stats['files_by_type'][log_type]['size'] += file_size
                
                # Track oldest and newest
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                if oldest_time is None or file_time < oldest_time:
                    oldest_time = file_time
                    stats['oldest_file'] = {'name': log_file.name, 'date': file_time}
                
                if newest_time is None or file_time > newest_time:
                    newest_time = file_time
                    stats['newest_file'] = {'name': log_file.name, 'date': file_time}
                
                # Track largest file
                if file_size > largest_size:
                    largest_size = file_size
                    stats['largest_file'] = {'name': log_file.name, 'size': file_size}
        
        return stats
    
    def perform_maintenance(self):
        """Perform complete log maintenance - rotation, compression, cleanup"""
        logger.info("Starting log maintenance...")
        
        maintenance_stats = {
            'rotated_files': 0,
            'compressed_files': 0,
            'removed_files': 0,
            'errors': []
        }
        
        try:
            # Rotate large log files
            active_logs = ['django.log', 'performance.log', 'security.log', 
                          'file_uploads.log', 'errors.log', 'queries.log']
            
            for log_name in active_logs:
                log_path = self.log_dir / log_name
                if self.rotate_log_file(log_path):
                    maintenance_stats['rotated_files'] += 1
            
            # Compress old logs
            compressed = self.compress_old_logs()
            maintenance_stats['compressed_files'] = compressed
            
            # Clean up very old logs
            removed = self.cleanup_old_logs()
            maintenance_stats['removed_files'] = removed
            
            logger.info(f"Log maintenance completed: "
                       f"rotated={maintenance_stats['rotated_files']}, "
                       f"compressed={maintenance_stats['compressed_files']}, "
                       f"removed={maintenance_stats['removed_files']}")
        
        except Exception as e:
            error_msg = f"Error during log maintenance: {e}"
            logger.error(error_msg)
            maintenance_stats['errors'].append(error_msg)
        
        return maintenance_stats
    
    def archive_logs(self, archive_dir=None, days_old=7):
        """Archive logs to a separate directory"""
        if archive_dir is None:
            archive_dir = self.log_dir / 'archive'
        
        archive_path = Path(archive_dir)
        archive_path.mkdir(exist_ok=True)
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        archived_count = 0
        
        for log_file in self.log_dir.glob('*.log'):
            try:
                # Skip current active log files
                if log_file.name in ['django.log', 'performance.log', 'security.log', 
                                   'file_uploads.log', 'errors.log', 'queries.log']:
                    continue
                
                # Check file age
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_time < cutoff_date:
                    # Move to archive
                    archive_file = archive_path / log_file.name
                    shutil.move(str(log_file), str(archive_file))
                    
                    logger.info(f"Archived log file: {log_file} -> {archive_file}")
                    archived_count += 1
            
            except Exception as e:
                logger.error(f"Error archiving log file {log_file}: {e}")
        
        return archived_count


def get_log_manager():
    """Get a configured log manager instance"""
    return LogManager()


def perform_log_maintenance():
    """Perform log maintenance - convenience function"""
    manager = get_log_manager()
    return manager.perform_maintenance()


def get_log_statistics():
    """Get log file statistics - convenience function"""
    manager = get_log_manager()
    return manager.get_log_file_stats()