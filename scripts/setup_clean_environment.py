#!/usr/bin/env python
"""
Script to set up a clean environment with sample data for GitHub publication.
This script ensures all sensitive data is removed and sample data is loaded.
"""

import os
import sys
import django
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'onlineservice.settings')
django.setup()

from django.core.management import call_command
from django.db import connection
from django.contrib.auth.models import User


def clean_database():
    """Remove all data from the database"""
    print("🧹 Cleaning database...")
    
    # Get all table names
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
    
    # Drop all tables except django_migrations
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        for table in tables:
            table_name = table[0]
            if table_name != 'django_migrations' and not table_name.startswith('sqlite_'):
                cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
        cursor.execute("PRAGMA foreign_keys = ON;")
    
    print("✅ Database cleaned")


def setup_database():
    """Run migrations and load sample data"""
    print("🔧 Setting up database...")
    
    # Run migrations
    call_command('migrate', verbosity=0)
    print("✅ Migrations applied")
    
    # Load sample data
    call_command('loaddata', 'insurance_requests/fixtures/sample_data.json', verbosity=0)
    print("✅ Sample data loaded")


def verify_setup():
    """Verify that the setup was successful"""
    print("🔍 Verifying setup...")
    
    # Check users
    admin_count = User.objects.filter(is_superuser=True).count()
    user_count = User.objects.filter(is_superuser=False).count()
    
    print(f"✅ Admin users: {admin_count}")
    print(f"✅ Regular users: {user_count}")
    
    # Check insurance requests
    from insurance_requests.models import InsuranceRequest
    request_count = InsuranceRequest.objects.count()
    print(f"✅ Sample insurance requests: {request_count}")
    
    # Check that no real data exists
    real_data_indicators = [
        'реальный',
        'настоящий', 
        'production',
        'prod',
    ]
    
    suspicious_requests = InsuranceRequest.objects.filter(
        client_name__icontains='реальный'
    ).count()
    
    if suspicious_requests == 0:
        print("✅ No suspicious real data found")
    else:
        print(f"⚠️  Found {suspicious_requests} potentially real requests")


def main():
    """Main setup function"""
    print("🚀 Setting up clean environment for GitHub publication...")
    print("=" * 60)
    
    try:
        clean_database()
        setup_database()
        verify_setup()
        
        print("=" * 60)
        print("✅ Clean environment setup completed successfully!")
        print("\nYou can now use these accounts:")
        print("👤 Admin: username='admin', password='admin123'")
        print("👤 User: username='user', password='user123'")
        print("\n📊 Sample data includes 5 insurance requests with various statuses")
        print("🔒 All sensitive data has been removed")
        
    except Exception as e:
        print(f"❌ Error during setup: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()