"""
Custom static file storage with compression and cache busting for production.
"""

import os
import gzip
import hashlib
from pathlib import Path
from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
from django.core.files.base import ContentFile
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class CompressedManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """
    Custom static files storage that provides:
    1. Automatic gzip compression for text-based files
    2. Cache busting with content-based hashing
    3. CDN-ready file serving
    4. Optimized file handling for production
    5. Static file minification
    6. Preload resource optimization
    """
    
    # File extensions that should be compressed
    COMPRESSIBLE_EXTENSIONS = {
        '.css', '.js', '.html', '.xml', '.json', '.txt', '.svg',
        '.map', '.md', '.csv', '.tsv', '.rss', '.atom'
    }
    
    # File extensions that should have long cache times
    CACHEABLE_EXTENSIONS = {
        '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg',
        '.woff', '.woff2', '.ttf', '.eot', '.ico', '.pdf', '.webp'
    }
    
    # File extensions that can be minified
    MINIFIABLE_EXTENSIONS = {
        '.css', '.js', '.html', '.xml', '.json', '.svg'
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.compressed_files = {}
        self.minified_files = {}
        self.optimization_stats = {
            'compressed': 0,
            'minified': 0,
            'total_size_before': 0,
            'total_size_after': 0
        }
        
    def post_process(self, paths, dry_run=False, **options):
        """
        Post-process static files with compression and optimization.
        """
        logger.info("Starting static file post-processing with compression and optimization")
        
        # First run the parent post_process for manifest generation
        processed_files = super().post_process(paths, dry_run, **options)
        
        if not dry_run:
            # Minify eligible files first
            if getattr(settings, 'STATIC_FILE_MINIFICATION', True):
                self._minify_files(paths)
            
            # Compress eligible files
            if getattr(settings, 'STATIC_FILE_COMPRESSION', True):
                self._compress_files(paths)
            
            # Generate optimized manifest
            self._optimize_manifest()
            
            # Log optimization statistics
            self._log_optimization_stats()
            
        logger.info("Static file post-processing completed")
        return processed_files
    
    def _minify_files(self, paths):
        """
        Minify CSS and JavaScript files.
        """
        minified_count = 0
        
        for path in paths:
            if self._should_minify(path):
                try:
                    if self._minify_file(path):
                        minified_count += 1
                except Exception as e:
                    logger.warning(f"Failed to minify {path}: {e}")
        
        logger.info(f"Minified {minified_count} static files")
        self.optimization_stats['minified'] = minified_count
    
    def _compress_files(self, paths):
        """
        Compress text-based static files with gzip.
        """
        compressed_count = 0
        
        for path in paths:
            if self._should_compress(path):
                try:
                    self._compress_file(path)
                    compressed_count += 1
                except Exception as e:
                    logger.warning(f"Failed to compress {path}: {e}")
        
        logger.info(f"Compressed {compressed_count} static files")
        self.optimization_stats['compressed'] = compressed_count
    
    def _should_compress(self, path):
        """
        Determine if a file should be compressed based on its extension.
        """
        file_path = Path(path)
        return file_path.suffix.lower() in self.COMPRESSIBLE_EXTENSIONS
    
    def _should_minify(self, path):
        """
        Determine if a file should be minified based on its extension.
        """
        file_path = Path(path)
        extension = file_path.suffix.lower()
        
        # Don't minify already minified files
        if '.min.' in file_path.name:
            return False
            
        return extension in self.MINIFIABLE_EXTENSIONS
    
    def _compress_file(self, path):
        """
        Create a gzipped version of the file.
        """
        if not self.exists(path):
            return
            
        # Read the original file
        with self.open(path, 'rb') as original_file:
            content = original_file.read()
        
        # Compress the content
        compressed_content = gzip.compress(content, compresslevel=9)
        
        # Only save if compression actually reduces size
        if len(compressed_content) < len(content):
            compressed_path = f"{path}.gz"
            compressed_file = ContentFile(compressed_content)
            
            # Save the compressed version
            self._save(compressed_path, compressed_file)
            self.compressed_files[path] = compressed_path
            
            logger.debug(f"Compressed {path} -> {compressed_path} "
                        f"({len(content)} -> {len(compressed_content)} bytes)")
    
    def _minify_file(self, path):
        """
        Minify a single file based on its type.
        """
        if not self.exists(path):
            return False
            
        try:
            # Read the original file
            with self.open(path, 'r', encoding='utf-8') as original_file:
                content = original_file.read()
            
            original_size = len(content.encode('utf-8'))
            self.optimization_stats['total_size_before'] += original_size
            
            # Minify based on file type
            file_path = Path(path)
            extension = file_path.suffix.lower()
            
            if extension == '.css':
                minified_content = self._minify_css(content)
            elif extension == '.js':
                minified_content = self._minify_js(content)
            elif extension == '.html':
                minified_content = self._minify_html(content)
            elif extension == '.json':
                minified_content = self._minify_json(content)
            elif extension == '.svg':
                minified_content = self._minify_svg(content)
            else:
                return False
            
            # Only save if minification actually reduces size
            minified_size = len(minified_content.encode('utf-8'))
            if minified_size < original_size:
                minified_file = ContentFile(minified_content.encode('utf-8'))
                self._save(path, minified_file)
                
                self.minified_files[path] = True
                self.optimization_stats['total_size_after'] += minified_size
                
                logger.debug(f"Minified {path} "
                           f"({original_size} -> {minified_size} bytes)")
                return True
            else:
                self.optimization_stats['total_size_after'] += original_size
                
        except Exception as e:
            logger.warning(f"Failed to minify {path}: {e}")
            
        return False
    
    def _optimize_manifest(self):
        """
        Optimize the manifest file for better performance.
        """
        if hasattr(self, 'manifest_name') and self.exists(self.manifest_name):
            try:
                # Add compression info to manifest if needed
                manifest = self.load_manifest()
                
                # Add metadata about compressed files
                if self.compressed_files:
                    manifest.setdefault('compressed', {})
                    manifest['compressed'].update(self.compressed_files)
                
                # Save the updated manifest
                self.save_manifest(manifest)
                
                logger.debug("Optimized static files manifest")
            except Exception as e:
                logger.warning(f"Failed to optimize manifest: {e}")
    
    def url(self, name, force=False):
        """
        Return the URL for a static file, with CDN support if configured.
        """
        url = super().url(name, force)
        
        # Add CDN prefix if configured
        cdn_url = getattr(settings, 'STATIC_CDN_URL', None)
        if cdn_url and not settings.DEBUG:
            # Replace the static URL with CDN URL
            static_url = settings.STATIC_URL.rstrip('/')
            if url.startswith(static_url):
                url = url.replace(static_url, cdn_url.rstrip('/'), 1)
        
        return url
    
    def get_cache_control_header(self, name):
        """
        Get appropriate cache control header for a file.
        """
        file_path = Path(name)
        extension = file_path.suffix.lower()
        
        if extension in self.CACHEABLE_EXTENSIONS:
            # Long cache for static assets with versioning
            return "public, max-age=31536000, immutable"  # 1 year
        else:
            # Shorter cache for other files
            return "public, max-age=86400"  # 1 day
    
    def get_content_encoding(self, name):
        """
        Get content encoding for compressed files.
        """
        if name in self.compressed_files:
            return "gzip"
        return None
    
    def _minify_css(self, content):
        """
        Minify CSS content.
        """
        import re
        
        # Remove comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Remove whitespace around specific characters
        content = re.sub(r'\s*([{}:;,>+~])\s*', r'\1', content)
        
        # Remove trailing semicolons before }
        content = re.sub(r';\s*}', '}', content)
        
        # Remove unnecessary quotes from URLs
        content = re.sub(r'url\(\s*["\']([^"\']*)["\']\s*\)', r'url(\1)', content)
        
        return content.strip()
    
    def _minify_js(self, content):
        """
        Basic JavaScript minification.
        """
        import re
        
        # Remove single-line comments (but preserve URLs)
        content = re.sub(r'(?<!:)//.*$', '', content, flags=re.MULTILINE)
        
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Remove extra whitespace but preserve line breaks for safety
        content = re.sub(r'[ \t]+', ' ', content)
        content = re.sub(r'\n\s*\n', '\n', content)
        
        # Remove whitespace around operators and punctuation
        content = re.sub(r'\s*([{}();,])\s*', r'\1', content)
        
        return content.strip()
    
    def _minify_html(self, content):
        """
        Basic HTML minification.
        """
        import re
        
        # Remove HTML comments (but preserve conditional comments)
        content = re.sub(r'<!--(?!\[if).*?-->', '', content, flags=re.DOTALL)
        
        # Remove extra whitespace between tags
        content = re.sub(r'>\s+<', '><', content)
        
        # Remove extra whitespace within tags
        content = re.sub(r'\s+', ' ', content)
        
        return content.strip()
    
    def _minify_json(self, content):
        """
        Minify JSON content.
        """
        import json
        try:
            # Parse and re-serialize without whitespace
            data = json.loads(content)
            return json.dumps(data, separators=(',', ':'))
        except json.JSONDecodeError:
            # If parsing fails, just remove extra whitespace
            import re
            content = re.sub(r'\s+', ' ', content)
            return content.strip()
    
    def _minify_svg(self, content):
        """
        Basic SVG minification.
        """
        import re
        
        # Remove XML comments
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
        
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Remove whitespace around tag boundaries
        content = re.sub(r'>\s+<', '><', content)
        
        return content.strip()
    
    def _log_optimization_stats(self):
        """
        Log optimization statistics.
        """
        stats = self.optimization_stats
        total_savings = stats['total_size_before'] - stats['total_size_after']
        
        if stats['total_size_before'] > 0:
            savings_percent = (total_savings / stats['total_size_before']) * 100
            
            logger.info(
                f"Static file optimization complete: "
                f"Compressed: {stats['compressed']} files, "
                f"Minified: {stats['minified']} files, "
                f"Size reduction: {total_savings:,} bytes ({savings_percent:.1f}%)"
            )


class CDNStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    Static files storage optimized for CDN usage.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cdn_url = getattr(settings, 'STATIC_CDN_URL', None)
        self.cdn_enabled = bool(self.cdn_url and not settings.DEBUG)
    
    def url(self, name, force=False):
        """
        Return CDN URL for static files in production.
        """
        if self.cdn_enabled:
            # Get the hashed filename from parent
            hashed_name = super().stored_name(name)
            return f"{self.cdn_url.rstrip('/')}/{hashed_name}"
        
        return super().url(name, force)
    
    def get_available_name(self, name, max_length=None):
        """
        Generate CDN-friendly filenames.
        """
        # Use parent's hashing for cache busting
        return super().get_available_name(name, max_length)


def get_static_file_hash(file_path):
    """
    Generate a hash for a static file for cache busting.
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
            return hashlib.md5(content).hexdigest()[:8]
    except (IOError, OSError):
        return None


def optimize_static_files():
    """
    Utility function to optimize static files after collection.
    """
    from django.core.management import call_command
    
    logger.info("Starting static files optimization")
    
    try:
        # Collect static files with post-processing
        call_command('collectstatic', '--noinput', '--clear')
        logger.info("Static files collected and optimized successfully")
        
        return True
    except Exception as e:
        logger.error(f"Failed to optimize static files: {e}")
        return False