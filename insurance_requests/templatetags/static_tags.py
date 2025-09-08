"""
Template tags for optimized static file handling with cache busting and CDN support.
"""

import os
import hashlib
from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.safestring import mark_safe
from django.templatetags.static import static
import logging

logger = logging.getLogger(__name__)
register = template.Library()


@register.simple_tag
def static_optimized(path):
    """
    Return an optimized static file URL with cache busting and CDN support.
    
    Usage: {% static_optimized 'css/style.css' %}
    """
    try:
        # Use Django's static file storage for proper URL generation
        url = staticfiles_storage.url(path)
        
        # Add CDN prefix if configured and not in debug mode
        if not settings.DEBUG:
            cdn_url = getattr(settings, 'STATIC_CDN_URL', None)
            if cdn_url:
                static_url = settings.STATIC_URL.rstrip('/')
                if url.startswith(static_url):
                    url = url.replace(static_url, cdn_url.rstrip('/'), 1)
        
        return url
        
    except Exception as e:
        logger.warning(f"Failed to generate optimized static URL for {path}: {e}")
        # Fallback to standard static tag
        return static(path)


@register.simple_tag
def static_preload_critical():
    """
    Generate preload tags for critical resources defined in settings.
    
    Usage: {% static_preload_critical %}
    """
    preload_resources = getattr(settings, 'STATIC_PRELOAD_RESOURCES', [])
    preload_tags = []
    
    for resource_path in preload_resources:
        try:
            url = static_optimized(resource_path)
            resource_type = _get_resource_type(resource_path)
            
            # Generate preload tag
            tag = f'<link rel="preload" href="{url}" as="{resource_type}"'
            
            # Add crossorigin for fonts
            if resource_type == 'font':
                tag += ' crossorigin="anonymous"'
            
            tag += '>'
            preload_tags.append(tag)
            
        except Exception as e:
            logger.warning(f"Failed to generate preload tag for {resource_path}: {e}")
    
    return mark_safe('\n'.join(preload_tags))


@register.simple_tag
def static_with_version(path):
    """
    Return a static file URL with version parameter for cache busting.
    
    Usage: {% static_with_version 'css/style.css' %}
    """
    try:
        base_url = static(path)
        
        # Add version parameter based on file modification time or content hash
        version = _get_file_version(path)
        if version:
            separator = '&' if '?' in base_url else '?'
            return f"{base_url}{separator}v={version}"
        
        return base_url
        
    except Exception as e:
        logger.warning(f"Failed to generate versioned static URL for {path}: {e}")
        return static(path)


@register.simple_tag
def preload_static(path, as_type=None, crossorigin=None):
    """
    Generate a preload link tag for a static resource.
    
    Usage: {% preload_static 'css/critical.css' 'style' %}
    """
    try:
        url = static_optimized(path)
        
        # Determine resource type if not specified
        if not as_type:
            as_type = _get_resource_type(path)
        
        # Build preload link tag
        attrs = [f'rel="preload"', f'href="{url}"', f'as="{as_type}"']
        
        if crossorigin:
            attrs.append(f'crossorigin="{crossorigin}"')
        
        return mark_safe(f'<link {" ".join(attrs)}>')
        
    except Exception as e:
        logger.warning(f"Failed to generate preload tag for {path}: {e}")
        return ''


@register.simple_tag
def inline_static(path, tag_type=None):
    """
    Inline a small static file directly into the template.
    
    Usage: {% inline_static 'css/critical.css' 'style' %}
    """
    try:
        # Only inline small files to avoid bloating HTML
        file_path = staticfiles_storage.path(path)
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            
            # Only inline files smaller than 10KB
            if file_size > 10 * 1024:
                logger.warning(f"File {path} too large to inline ({file_size} bytes)")
                return static_optimized(path)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Determine tag type if not specified
            if not tag_type:
                tag_type = _get_inline_tag_type(path)
            
            if tag_type == 'style':
                return mark_safe(f'<style>{content}</style>')
            elif tag_type == 'script':
                return mark_safe(f'<script>{content}</script>')
            else:
                return content
        
    except Exception as e:
        logger.warning(f"Failed to inline static file {path}: {e}")
    
    # Fallback to regular static URL
    return static_optimized(path)


@register.simple_tag
def static_integrity(path):
    """
    Generate integrity hash for a static file (for SRI - Subresource Integrity).
    
    Usage: <link rel="stylesheet" href="{% static_optimized 'css/style.css' %}" integrity="{% static_integrity 'css/style.css' %}">
    """
    try:
        file_path = staticfiles_storage.path(path)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                content = f.read()
            
            # Generate SHA384 hash for integrity
            hash_value = hashlib.sha384(content).digest()
            import base64
            return f"sha384-{base64.b64encode(hash_value).decode()}"
        
    except Exception as e:
        logger.warning(f"Failed to generate integrity hash for {path}: {e}")
    
    return ''


@register.inclusion_tag('insurance_requests/static_css.html')
def load_css(path, media='all', preload=False):
    """
    Load CSS with optimization features.
    
    Usage: {% load_css 'css/style.css' media='screen' preload=True %}
    """
    return {
        'url': static_optimized(path),
        'media': media,
        'preload': preload,
        'integrity': static_integrity(path) if not settings.DEBUG else '',
    }


@register.inclusion_tag('insurance_requests/static_js.html')
def load_js(path, defer=True, async_load=False, integrity=True):
    """
    Load JavaScript with optimization features.
    
    Usage: {% load_js 'js/app.js' defer=True async=False %}
    """
    return {
        'url': static_optimized(path),
        'defer': defer,
        'async': async_load,
        'integrity': static_integrity(path) if integrity and not settings.DEBUG else '',
    }


@register.simple_tag
def static_resource_hints(dns_prefetch=None, preconnect=None):
    """
    Generate resource hints for external domains.
    
    Usage: {% static_resource_hints dns_prefetch="fonts.googleapis.com" preconnect="cdn.example.com" %}
    """
    hints = []
    
    # DNS prefetch hints
    if dns_prefetch:
        domains = dns_prefetch.split(',')
        for domain in domains:
            domain = domain.strip()
            hints.append(f'<link rel="dns-prefetch" href="//{domain}">')
    
    # Preconnect hints
    if preconnect:
        domains = preconnect.split(',')
        for domain in domains:
            domain = domain.strip()
            hints.append(f'<link rel="preconnect" href="https://{domain}" crossorigin>')
    
    # Add CDN preconnect if configured
    cdn_url = getattr(settings, 'STATIC_CDN_URL', None)
    if cdn_url and not settings.DEBUG:
        from urllib.parse import urlparse
        cdn_domain = urlparse(cdn_url).netloc
        if cdn_domain:
            hints.append(f'<link rel="preconnect" href="https://{cdn_domain}" crossorigin>')
    
    return mark_safe('\n'.join(hints))


@register.simple_tag
def static_manifest_json():
    """
    Generate web app manifest link if available.
    
    Usage: {% static_manifest_json %}
    """
    try:
        manifest_url = static_optimized('manifest.json')
        return mark_safe(f'<link rel="manifest" href="{manifest_url}">')
    except Exception:
        return ''


def _get_file_version(path):
    """Get version string for a static file based on modification time."""
    try:
        file_path = staticfiles_storage.path(path)
        if os.path.exists(file_path):
            mtime = os.path.getmtime(file_path)
            return str(int(mtime))
    except Exception:
        pass
    
    return None


def _get_resource_type(path):
    """Determine resource type for preload based on file extension."""
    extension = os.path.splitext(path)[1].lower()
    
    type_map = {
        '.css': 'style',
        '.js': 'script',
        '.woff': 'font',
        '.woff2': 'font',
        '.ttf': 'font',
        '.eot': 'font',
        '.png': 'image',
        '.jpg': 'image',
        '.jpeg': 'image',
        '.gif': 'image',
        '.svg': 'image',
        '.webp': 'image',
    }
    
    return type_map.get(extension, 'fetch')


def _get_inline_tag_type(path):
    """Determine tag type for inlining based on file extension."""
    extension = os.path.splitext(path)[1].lower()
    
    if extension == '.css':
        return 'style'
    elif extension == '.js':
        return 'script'
    else:
        return 'text'