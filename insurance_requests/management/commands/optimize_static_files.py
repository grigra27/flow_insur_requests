"""
Management command to optimize static files for production deployment.
"""

import os
import gzip
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.management.commands.collectstatic import Command as CollectStaticCommand
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Optimize static files for production with compression and cache busting'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--compress',
            action='store_true',
            help='Enable gzip compression for text-based files',
        )
        parser.add_argument(
            '--minify',
            action='store_true',
            help='Minify CSS and JavaScript files',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing static files before optimization',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually doing it',
        )
        parser.add_argument(
            '--generate-manifest',
            action='store_true',
            help='Generate web app manifest.json file',
        )
        parser.add_argument(
            '--create-service-worker',
            action='store_true',
            help='Create basic service worker for caching',
        )
        parser.add_argument(
            '--analyze',
            action='store_true',
            help='Analyze static files and generate optimization report',
        )
        parser.add_argument(
            '--verbosity',
            type=int,
            choices=[0, 1, 2, 3],
            default=1,
            help='Verbosity level',
        )
    
    def handle(self, *args, **options):
        self.verbosity = options['verbosity']
        self.dry_run = options['dry_run']
        
        if self.verbosity >= 1:
            self.stdout.write("Starting static file optimization...")
        
        try:
            # Clear existing files if requested
            if options['clear']:
                self._clear_static_files()
            
            # Collect static files first
            self._collect_static_files()
            
            # Compress files if requested
            if options['compress']:
                self._compress_static_files()
            
            # Minify files if requested
            if options['minify']:
                self._minify_static_files()
            
            # Generate web app manifest if requested
            if options['generate_manifest']:
                self._generate_web_manifest()
            
            # Create service worker if requested
            if options['create_service_worker']:
                self._create_service_worker()
            
            # Analyze files if requested
            if options['analyze']:
                self._analyze_static_files()
            
            # Generate optimization report
            self._generate_report()
            
            if self.verbosity >= 1:
                self.stdout.write(
                    self.style.SUCCESS("Static file optimization completed successfully!")
                )
                
        except Exception as e:
            logger.error(f"Static file optimization failed: {e}")
            raise CommandError(f"Optimization failed: {e}")
    
    def _clear_static_files(self):
        """Clear existing static files."""
        if self.verbosity >= 1:
            self.stdout.write("Clearing existing static files...")
        
        if not self.dry_run and settings.STATIC_ROOT and os.path.exists(settings.STATIC_ROOT):
            shutil.rmtree(settings.STATIC_ROOT)
            os.makedirs(settings.STATIC_ROOT, exist_ok=True)
    
    def _collect_static_files(self):
        """Collect static files using Django's collectstatic."""
        if self.verbosity >= 1:
            self.stdout.write("Collecting static files...")
        
        if not self.dry_run:
            from django.core.management import call_command
            call_command('collectstatic', '--noinput', verbosity=self.verbosity-1)
    
    def _compress_static_files(self):
        """Compress text-based static files with gzip."""
        if self.verbosity >= 1:
            self.stdout.write("Compressing static files...")
        
        if not settings.STATIC_ROOT:
            self.stdout.write(
                self.style.WARNING("STATIC_ROOT not set, skipping compression")
            )
            return
        
        compressible_extensions = {'.css', '.js', '.html', '.xml', '.json', '.txt', '.svg', '.map'}
        compressed_count = 0
        total_original_size = 0
        total_compressed_size = 0
        
        static_root = Path(settings.STATIC_ROOT)
        
        for file_path in static_root.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in compressible_extensions:
                if self._compress_file(file_path):
                    compressed_count += 1
                    
                    # Calculate size savings
                    original_size = file_path.stat().st_size
                    compressed_path = file_path.with_suffix(file_path.suffix + '.gz')
                    if compressed_path.exists():
                        compressed_size = compressed_path.stat().st_size
                        total_original_size += original_size
                        total_compressed_size += compressed_size
        
        if self.verbosity >= 1:
            savings = total_original_size - total_compressed_size
            savings_percent = (savings / total_original_size * 100) if total_original_size > 0 else 0
            
            self.stdout.write(
                f"Compressed {compressed_count} files. "
                f"Size reduction: {savings:,} bytes ({savings_percent:.1f}%)"
            )
    
    def _compress_file(self, file_path):
        """Compress a single file with gzip."""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            compressed_content = gzip.compress(content, compresslevel=9)
            
            # Only save if compression actually reduces size
            if len(compressed_content) < len(content):
                compressed_path = file_path.with_suffix(file_path.suffix + '.gz')
                
                if not self.dry_run:
                    with open(compressed_path, 'wb') as f:
                        f.write(compressed_content)
                
                if self.verbosity >= 2:
                    self.stdout.write(f"Compressed: {file_path.relative_to(settings.STATIC_ROOT)}")
                
                return True
            
        except Exception as e:
            if self.verbosity >= 1:
                self.stdout.write(
                    self.style.WARNING(f"Failed to compress {file_path}: {e}")
                )
        
        return False
    
    def _minify_static_files(self):
        """Minify CSS and JavaScript files."""
        if self.verbosity >= 1:
            self.stdout.write("Minifying CSS and JavaScript files...")
        
        if not settings.STATIC_ROOT:
            self.stdout.write(
                self.style.WARNING("STATIC_ROOT not set, skipping minification")
            )
            return
        
        minified_count = 0
        static_root = Path(settings.STATIC_ROOT)
        
        # Minify CSS files
        for css_file in static_root.rglob('*.css'):
            if not css_file.name.endswith('.min.css'):
                if self._minify_css_file(css_file):
                    minified_count += 1
        
        # Minify JavaScript files
        for js_file in static_root.rglob('*.js'):
            if not js_file.name.endswith('.min.js'):
                if self._minify_js_file(js_file):
                    minified_count += 1
        
        if self.verbosity >= 1:
            self.stdout.write(f"Minified {minified_count} files")
    
    def _minify_css_file(self, file_path):
        """Basic CSS minification."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Basic CSS minification
            minified = self._basic_css_minify(content)
            
            if len(minified) < len(content):
                if not self.dry_run:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(minified)
                
                if self.verbosity >= 2:
                    self.stdout.write(f"Minified CSS: {file_path.relative_to(settings.STATIC_ROOT)}")
                
                return True
                
        except Exception as e:
            if self.verbosity >= 1:
                self.stdout.write(
                    self.style.WARNING(f"Failed to minify CSS {file_path}: {e}")
                )
        
        return False
    
    def _minify_js_file(self, file_path):
        """Basic JavaScript minification."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Basic JavaScript minification
            minified = self._basic_js_minify(content)
            
            if len(minified) < len(content):
                if not self.dry_run:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(minified)
                
                if self.verbosity >= 2:
                    self.stdout.write(f"Minified JS: {file_path.relative_to(settings.STATIC_ROOT)}")
                
                return True
                
        except Exception as e:
            if self.verbosity >= 1:
                self.stdout.write(
                    self.style.WARNING(f"Failed to minify JS {file_path}: {e}")
                )
        
        return False
    
    def _basic_css_minify(self, content):
        """Basic CSS minification - remove comments, whitespace, etc."""
        import re
        
        # Remove comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Remove whitespace around specific characters
        content = re.sub(r'\s*([{}:;,>+~])\s*', r'\1', content)
        
        # Remove trailing semicolons before }
        content = re.sub(r';\s*}', '}', content)
        
        return content.strip()
    
    def _basic_js_minify(self, content):
        """Basic JavaScript minification - remove comments and extra whitespace."""
        import re
        
        # Remove single-line comments (but preserve URLs)
        content = re.sub(r'(?<!:)//.*$', '', content, flags=re.MULTILINE)
        
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Remove extra whitespace but preserve line breaks for safety
        content = re.sub(r'[ \t]+', ' ', content)
        content = re.sub(r'\n\s*\n', '\n', content)
        
        return content.strip()
    
    def _generate_report(self):
        """Generate optimization report."""
        if not settings.STATIC_ROOT or not os.path.exists(settings.STATIC_ROOT):
            return
        
        static_root = Path(settings.STATIC_ROOT)
        
        # Count files by type
        file_counts = {}
        total_size = 0
        compressed_files = 0
        
        for file_path in static_root.rglob('*'):
            if file_path.is_file():
                extension = file_path.suffix.lower()
                file_counts[extension] = file_counts.get(extension, 0) + 1
                total_size += file_path.stat().st_size
                
                if file_path.suffix == '.gz':
                    compressed_files += 1
        
        if self.verbosity >= 1:
            self.stdout.write("\n" + "="*50)
            self.stdout.write("STATIC FILES OPTIMIZATION REPORT")
            self.stdout.write("="*50)
            self.stdout.write(f"Total files: {sum(file_counts.values())}")
            self.stdout.write(f"Total size: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")
            self.stdout.write(f"Compressed files: {compressed_files}")
            
            if file_counts:
                self.stdout.write("\nFile types:")
                for ext, count in sorted(file_counts.items()):
                    self.stdout.write(f"  {ext or '(no extension)'}: {count}")
            
            self.stdout.write("="*50)
    
    def _generate_web_manifest(self):
        """Generate a web app manifest.json file."""
        if self.verbosity >= 1:
            self.stdout.write("Generating web app manifest...")
        
        manifest = {
            "name": "Insurance Request System",
            "short_name": "Insurance App",
            "description": "Insurance request management system",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#007bff",
            "icons": [
                {
                    "src": "/static/icons/icon-192x192.png",
                    "sizes": "192x192",
                    "type": "image/png"
                },
                {
                    "src": "/static/icons/icon-512x512.png",
                    "sizes": "512x512",
                    "type": "image/png"
                }
            ]
        }
        
        if not self.dry_run and settings.STATIC_ROOT:
            import json
            manifest_path = Path(settings.STATIC_ROOT) / 'manifest.json'
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            
            if self.verbosity >= 1:
                self.stdout.write(f"Generated manifest.json at {manifest_path}")
    
    def _create_service_worker(self):
        """Create a basic service worker for static file caching."""
        if self.verbosity >= 1:
            self.stdout.write("Creating service worker...")
        
        service_worker_content = '''
// Service Worker for static file caching
const CACHE_NAME = 'insurance-app-v1';
const STATIC_CACHE_URLS = [
    '/',
    '/static/css/custom.css',
    '/static/js/app.js',
    // Add other critical static files here
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(STATIC_CACHE_URLS))
    );
});

self.addEventListener('fetch', event => {
    // Only cache GET requests for static files
    if (event.request.method === 'GET' && 
        (event.request.url.includes('/static/') || 
         event.request.url.includes('/media/'))) {
        
        event.respondWith(
            caches.match(event.request)
                .then(response => {
                    // Return cached version or fetch from network
                    return response || fetch(event.request);
                })
        );
    }
});
'''.strip()
        
        if not self.dry_run and settings.STATIC_ROOT:
            sw_path = Path(settings.STATIC_ROOT) / 'sw.js'
            with open(sw_path, 'w', encoding='utf-8') as f:
                f.write(service_worker_content)
            
            if self.verbosity >= 1:
                self.stdout.write(f"Created service worker at {sw_path}")
    
    def _analyze_static_files(self):
        """Analyze static files and provide optimization recommendations."""
        if self.verbosity >= 1:
            self.stdout.write("Analyzing static files...")
        
        if not settings.STATIC_ROOT or not os.path.exists(settings.STATIC_ROOT):
            self.stdout.write(
                self.style.WARNING("STATIC_ROOT not found, skipping analysis")
            )
            return
        
        static_root = Path(settings.STATIC_ROOT)
        analysis = {
            'total_files': 0,
            'total_size': 0,
            'large_files': [],
            'uncompressed_files': [],
            'optimization_opportunities': []
        }
        
        for file_path in static_root.rglob('*'):
            if file_path.is_file():
                analysis['total_files'] += 1
                file_size = file_path.stat().st_size
                analysis['total_size'] += file_size
                
                # Check for large files (>100KB)
                if file_size > 100 * 1024:
                    analysis['large_files'].append({
                        'path': file_path.relative_to(static_root),
                        'size': file_size
                    })
                
                # Check for uncompressed text files
                if (file_path.suffix.lower() in {'.css', '.js', '.html', '.json'} and
                    not file_path.with_suffix(file_path.suffix + '.gz').exists()):
                    analysis['uncompressed_files'].append(
                        file_path.relative_to(static_root)
                    )
        
        # Generate recommendations
        if analysis['large_files']:
            analysis['optimization_opportunities'].append(
                f"Consider compressing {len(analysis['large_files'])} large files"
            )
        
        if analysis['uncompressed_files']:
            analysis['optimization_opportunities'].append(
                f"Enable compression for {len(analysis['uncompressed_files'])} text files"
            )
        
        # Display analysis results
        if self.verbosity >= 1:
            self.stdout.write("\n" + "="*50)
            self.stdout.write("STATIC FILES ANALYSIS")
            self.stdout.write("="*50)
            self.stdout.write(f"Total files: {analysis['total_files']}")
            self.stdout.write(f"Total size: {analysis['total_size']:,} bytes "
                            f"({analysis['total_size']/1024/1024:.1f} MB)")
            
            if analysis['large_files']:
                self.stdout.write(f"\nLarge files (>100KB): {len(analysis['large_files'])}")
                for file_info in analysis['large_files'][:5]:  # Show top 5
                    self.stdout.write(f"  {file_info['path']}: "
                                    f"{file_info['size']:,} bytes")
            
            if analysis['optimization_opportunities']:
                self.stdout.write("\nOptimization opportunities:")
                for opportunity in analysis['optimization_opportunities']:
                    self.stdout.write(f"  • {opportunity}")
            
            self.stdout.write("="*50)