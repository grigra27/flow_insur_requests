"""
Template tags for security features like CSP nonces.
"""

from django import template
from django.utils.safestring import mark_safe
from django.conf import settings
import logging

register = template.Library()
logger = logging.getLogger('security')


@register.simple_tag(takes_context=True)
def csp_nonce(context):
    """
    Get the CSP nonce for the current request.
    
    Usage in templates:
    {% load security_tags %}
    <script nonce="{% csp_nonce %}">
        // Your inline script here
    </script>
    """
    request = context.get('request')
    if request and hasattr(request, 'csp_nonce'):
        return request.csp_nonce
    return ''


@register.simple_tag(takes_context=True)
def csp_script_tag(context, content=''):
    """
    Create a script tag with proper CSP nonce.
    
    Usage in templates:
    {% load security_tags %}
    {% csp_script_tag "console.log('Hello World');" %}
    """
    nonce = csp_nonce(context)
    if nonce:
        return mark_safe(f'<script nonce="{nonce}">{content}</script>')
    else:
        return mark_safe(f'<script>{content}</script>')


@register.simple_tag(takes_context=True)
def csp_style_tag(context, content=''):
    """
    Create a style tag with proper CSP nonce.
    
    Usage in templates:
    {% load security_tags %}
    {% csp_style_tag "body { margin: 0; }" %}
    """
    nonce = csp_nonce(context)
    if nonce:
        return mark_safe(f'<style nonce="{nonce}">{content}</style>')
    else:
        return mark_safe(f'<style>{content}</style>')


@register.inclusion_tag('insurance_requests/security_meta.html', takes_context=True)
def security_meta_tags(context):
    """
    Include security-related meta tags.
    
    Usage in templates:
    {% load security_tags %}
    {% security_meta_tags %}
    """
    request = context.get('request')
    
    return {
        'csp_nonce': getattr(request, 'csp_nonce', ''),
        'debug': getattr(settings, 'DEBUG', False),
        'secure_ssl_redirect': getattr(settings, 'SECURE_SSL_REDIRECT', False),
    }


@register.filter
def add_csp_nonce(script_tag, request):
    """
    Add CSP nonce to existing script tags.
    
    Usage in templates:
    {% load security_tags %}
    {{ my_script_tag|add_csp_nonce:request }}
    """
    if not hasattr(request, 'csp_nonce'):
        return script_tag
    
    nonce = request.csp_nonce
    
    # Add nonce to script tags
    if '<script' in script_tag and 'nonce=' not in script_tag:
        script_tag = script_tag.replace('<script', f'<script nonce="{nonce}"', 1)
    
    # Add nonce to style tags
    if '<style' in script_tag and 'nonce=' not in script_tag:
        script_tag = script_tag.replace('<style', f'<style nonce="{nonce}"', 1)
    
    return mark_safe(script_tag)


@register.simple_tag
def security_headers_status():
    """
    Get the status of security headers configuration.
    Useful for debugging and monitoring.
    """
    status = {
        'hsts_enabled': getattr(settings, 'SECURE_HSTS_SECONDS', 0) > 0,
        'csp_enabled': bool(getattr(settings, 'SECURE_CONTENT_SECURITY_POLICY', '')),
        'ssl_redirect': getattr(settings, 'SECURE_SSL_REDIRECT', False),
        'secure_cookies': getattr(settings, 'SESSION_COOKIE_SECURE', False),
        'csrf_secure': getattr(settings, 'CSRF_COOKIE_SECURE', False),
    }
    
    return status


@register.simple_tag
def csp_report_uri():
    """
    Get the CSP report URI if configured.
    """
    return getattr(settings, 'CSP_REPORT_URI', '')


@register.simple_tag(takes_context=True)
def inline_script_with_nonce(context, script_content):
    """
    Create an inline script with proper CSP nonce and error handling.
    
    Usage:
    {% load security_tags %}
    {% inline_script_with_nonce "console.log('test');" %}
    """
    request = context.get('request')
    nonce = getattr(request, 'csp_nonce', '')
    
    # Wrap script content with error handling
    wrapped_content = f"""
    try {{
        {script_content}
    }} catch (error) {{
        console.error('Inline script error:', error);
        if (window.reportError) {{
            window.reportError('inline_script', error);
        }}
    }}
    """
    
    if nonce:
        return mark_safe(f'<script nonce="{nonce}">{wrapped_content}</script>')
    else:
        return mark_safe(f'<script>{wrapped_content}</script>')


@register.simple_tag
def preload_resource(href, as_type='script', crossorigin='anonymous'):
    """
    Create a preload link with proper security attributes.
    
    Usage:
    {% load security_tags %}
    {% preload_resource "/static/js/app.js" "script" %}
    """
    integrity = ''
    
    # Add integrity attribute for external resources
    if href.startswith('http'):
        # In production, you would calculate or retrieve the actual integrity hash
        # For now, we'll just add the attribute structure
        if getattr(settings, 'STATIC_FILE_INTEGRITY', False):
            integrity = f' integrity="sha384-{href[-16:]}"'  # Placeholder
    
    crossorigin_attr = f' crossorigin="{crossorigin}"' if crossorigin else ''
    
    return mark_safe(
        f'<link rel="preload" href="{href}" as="{as_type}"{crossorigin_attr}{integrity}>'
    )