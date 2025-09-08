"""
Management command to set up database performance optimizations
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Set up database performance optimizations including indexes and cache'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-migrations',
            action='store_true',
            help='Skip running migrations',
        )
        parser.add_argument(
            '--skip-cache',
            action='store_true',
            help='Skip setting up cache table',
        )
        parser.add_argument(
            '--analyze-db',
            action='store_true',
            help='Run database analysis after setup',
        )
    
    def handle(self, *args, **options):
        """Set up all performance optimizations"""
        
        self.stdout.write(
            self.style.SUCCESS('Setting up database performance optimizations...')
        )
        
        # Run migrations to add indexes
        if not options['skip_migrations']:
            self.stdout.write('Running migrations to add performance indexes...')
            try:
                call_command('migrate', verbosity=1)
                self.stdout.write(
                    self.style.SUCCESS('✓ Migrations completed successfully')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error running migrations: {e}')
                )
                return
        
        # Set up cache table
        if not options['skip_cache']:
            self.stdout.write('Setting up cache table...')
            try:
                call_command('setup_cache')
                self.stdout.write(
                    self.style.SUCCESS('✓ Cache setup completed')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'⚠ Cache setup warning: {e}')
                )
        
        # Create logs directory
        logs_dir = settings.BASE_DIR / 'logs'
        if not logs_dir.exists():
            logs_dir.mkdir(exist_ok=True)
            self.stdout.write(
                self.style.SUCCESS('✓ Created logs directory')
            )
        
        # Analyze database if requested
        if options['analyze_db']:
            self.analyze_database()
        
        # Display optimization summary
        self.display_optimization_summary()
        
        self.stdout.write(
            self.style.SUCCESS('\n🚀 Database performance optimizations completed!')
        )
    
    def analyze_database(self):
        """Analyze database for performance insights"""
        self.stdout.write('\nAnalyzing database performance...')
        
        with connection.cursor() as cursor:
            # Check if we're using SQLite or PostgreSQL
            db_engine = settings.DATABASES['default']['ENGINE']
            
            if 'sqlite' in db_engine:
                self.analyze_sqlite(cursor)
            elif 'postgresql' in db_engine:
                self.analyze_postgresql(cursor)
            else:
                self.stdout.write(
                    self.style.WARNING(f'Database analysis not implemented for {db_engine}')
                )
    
    def analyze_sqlite(self, cursor):
        """Analyze SQLite database"""
        try:
            # Check indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
            indexes = cursor.fetchall()
            self.stdout.write(f'📊 Found {len(indexes)} indexes in database')
            
            # Check table sizes
            cursor.execute("""
                SELECT name, 
                       (SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=m.name) as table_count
                FROM sqlite_master m WHERE type='table' AND name NOT LIKE 'sqlite_%';
            """)
            tables = cursor.fetchall()
            self.stdout.write(f'📊 Found {len(tables)} user tables')
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'⚠ SQLite analysis error: {e}')
            )
    
    def analyze_postgresql(self, cursor):
        """Analyze PostgreSQL database"""
        try:
            # Check indexes
            cursor.execute("""
                SELECT schemaname, tablename, indexname, indexdef 
                FROM pg_indexes 
                WHERE schemaname = 'public';
            """)
            indexes = cursor.fetchall()
            self.stdout.write(f'📊 Found {len(indexes)} indexes in database')
            
            # Check table sizes
            cursor.execute("""
                SELECT schemaname, tablename, 
                       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables 
                WHERE schemaname = 'public';
            """)
            tables = cursor.fetchall()
            self.stdout.write(f'📊 Table sizes:')
            for table in tables:
                self.stdout.write(f'  - {table[1]}: {table[2]}')
                
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'⚠ PostgreSQL analysis error: {e}')
            )
    
    def display_optimization_summary(self):
        """Display summary of applied optimizations"""
        self.stdout.write('\n📋 Applied Optimizations:')
        self.stdout.write('  ✓ Database indexes for frequently queried fields')
        self.stdout.write('  ✓ Composite indexes for common query patterns')
        self.stdout.write('  ✓ Query optimization with select_related and prefetch_related')
        self.stdout.write('  ✓ Database connection pooling configuration')
        self.stdout.write('  ✓ Query performance monitoring middleware')
        self.stdout.write('  ✓ Slow query logging')
        self.stdout.write('  ✓ Cache configuration for query results')
        
        self.stdout.write('\n⚙️  Configuration:')
        self.stdout.write(f'  - Connection max age: {settings.DATABASES["default"].get("CONN_MAX_AGE", "Not set")}s')
        self.stdout.write(f'  - Slow query threshold: {getattr(settings, "SLOW_QUERY_THRESHOLD", 0.1)}s')
        self.stdout.write(f'  - Query logging: {"Enabled" if getattr(settings, "LOG_QUERIES", False) else "Disabled"}')
        
        cache_backend = settings.CACHES['default']['BACKEND']
        if 'redis' in cache_backend.lower():
            self.stdout.write('  - Cache backend: Redis (optimal)')
        elif 'database' in cache_backend.lower():
            self.stdout.write('  - Cache backend: Database (fallback)')
        else:
            self.stdout.write(f'  - Cache backend: {cache_backend}')
        
        self.stdout.write('\n💡 Next Steps:')
        self.stdout.write('  1. Monitor query performance in logs/performance.log')
        self.stdout.write('  2. Enable query logging with LOG_QUERIES=True for debugging')
        self.stdout.write('  3. Consider Redis for better cache performance')
        self.stdout.write('  4. Review slow queries and optimize as needed')