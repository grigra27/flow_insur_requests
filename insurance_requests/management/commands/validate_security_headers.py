"""
Management command to validate security headers configuration.
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.test import RequestFactory
from django.http import HttpResponse
from onlineservice.middleware import HTTPSSecurityMiddleware, CSPNonceMiddleware
import re
import logging

logger = logging.getLogger('security')


class Command(BaseCommand):
    help = 'Validate security headers configuration and test CSP policies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check-csp',
            action='store_true',
            help='Check Content Security Policy syntax',
        )
        parser.add_argument(
            '--test-headers',
            action='store_true',
            help='Test security headers middleware',
        )
        parser.add_argument(
            '--validate-hsts',
            action='store_true',
            help='Validate HSTS configuration',
        )
        parser.add_argument(
            '--check-cors',
            action='store_true',
            help='Check CORS configuration',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Verbose output',
        )

    def handle(self, *args, **options):
        self.verbose = options['verbose']
        
        self.stdout.write(
            self.style.SUCCESS('🔒 Security Headers Validation')
        )
        self.stdout.write('=' * 50)
        
        # Run all checks if no specific check is requested
        if not any([
            options['check_csp'],
            options['test_headers'],
            options['validate_hsts'],
            options['check_cors']
        ]):
            options.update({
                'check_csp': True,
                'test_headers': True,
                'validate_hsts': True,
                'check_cors': True,
            })
        
        try:
            if options['check_csp']:
                self.check_csp_configuration()
            
            if options['test_headers']:
                self.test_security_headers()
            
            if options['validate_hsts']:
                self.validate_hsts_configuration()
            
            if options['check_cors']:
                self.check_cors_configuration()
            
            self.stdout.write(
                self.style.SUCCESS('\n✅ Security validation completed successfully!')
            )
            
        except Exception as e:
            logger.error(f"Security validation failed: {e}")
            raise CommandError(f'Security validation failed: {e}')

    def check_csp_configuration(self):
        """Check Content Security Policy configuration."""
        self.stdout.write('\n📋 Checking Content Security Policy...')
        
        csp = getattr(settings, 'SECURE_CONTENT_SECURITY_POLICY', '')
        if not csp:
            self.stdout.write(
                self.style.WARNING('⚠️  No CSP configured')
            )
            return
        
        # Parse CSP directives
        directives = {}
        for directive in csp.split(';'):
            directive = directive.strip()
            if directive:
                parts = directive.split()
                if parts:
                    directives[parts[0]] = parts[1:] if len(parts) > 1 else []
        
        # Check essential directives
        essential_directives = [
            'default-src', 'script-src', 'style-src', 'img-src', 'font-src'
        ]
        
        for directive in essential_directives:
            if directive in directives:
                sources = directives[directive]
                self.stdout.write(f'  ✅ {directive}: {" ".join(sources)}')
                
                # Check for unsafe directives
                if "'unsafe-inline'" in sources:
                    self.stdout.write(
                        self.style.WARNING(f'    ⚠️  {directive} allows unsafe-inline')
                    )
                if "'unsafe-eval'" in sources:
                    self.stdout.write(
                        self.style.WARNING(f'    ⚠️  {directive} allows unsafe-eval')
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠️  Missing {directive} directive')
                )
        
        # Check for security-enhancing directives
        security_directives = {
            'upgrade-insecure-requests': 'Upgrades HTTP to HTTPS',
            'block-all-mixed-content': 'Blocks mixed content',
            'frame-ancestors': 'Controls embedding',
            'base-uri': 'Restricts base tag',
            'form-action': 'Restricts form submissions',
        }
        
        for directive, description in security_directives.items():
            if directive in directives or directive in csp:
                self.stdout.write(f'  ✅ {directive}: {description}')
            else:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠️  Consider adding {directive}: {description}')
                )
        
        # Check admin CSP
        admin_csp = getattr(settings, 'SECURE_CONTENT_SECURITY_POLICY_ADMIN', '')
        if admin_csp:
            self.stdout.write('  ✅ Separate admin CSP configured')
        else:
            self.stdout.write(
                self.style.WARNING('  ⚠️  No separate admin CSP configured')
            )

    def test_security_headers(self):
        """Test security headers middleware."""
        self.stdout.write('\n🛡️  Testing Security Headers Middleware...')
        
        factory = RequestFactory()
        
        # Test regular request
        request = factory.get('/')
        response = HttpResponse()
        
        # Apply middleware
        https_middleware = HTTPSSecurityMiddleware(lambda r: response)
        csp_middleware = CSPNonceMiddleware(lambda r: response)
        
        # Process request through CSP middleware
        csp_middleware.process_request(request)
        
        # Check if nonce was generated
        if hasattr(request, 'csp_nonce'):
            self.stdout.write('  ✅ CSP nonce generated')
            if self.verbose:
                self.stdout.write(f'    Nonce: {request.csp_nonce}')
        else:
            self.stdout.write(
                self.style.WARNING('  ⚠️  CSP nonce not generated')
            )
        
        # Simulate HTTPS environment
        settings.SECURE_SSL_REDIRECT = True
        
        # Process response through HTTPS middleware
        response = https_middleware.process_response(request, response)
        
        # Check headers
        expected_headers = [
            'Content-Security-Policy',
            'X-Frame-Options',
            'X-Content-Type-Options',
            'X-XSS-Protection',
            'Referrer-Policy',
            'Cross-Origin-Opener-Policy',
            'Permissions-Policy',
        ]
        
        for header in expected_headers:
            if header in response:
                self.stdout.write(f'  ✅ {header}: {response[header][:50]}...')
            else:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠️  Missing {header}')
                )
        
        # Test HSTS
        hsts_seconds = getattr(settings, 'SECURE_HSTS_SECONDS', 0)
        if hsts_seconds > 0:
            if 'Strict-Transport-Security' in response:
                self.stdout.write(f'  ✅ HSTS: {response["Strict-Transport-Security"]}')
            else:
                self.stdout.write(
                    self.style.WARNING('  ⚠️  HSTS configured but header missing')
                )

    def validate_hsts_configuration(self):
        """Validate HSTS configuration."""
        self.stdout.write('\n🔒 Validating HSTS Configuration...')
        
        hsts_seconds = getattr(settings, 'SECURE_HSTS_SECONDS', 0)
        include_subdomains = getattr(settings, 'SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
        preload = getattr(settings, 'SECURE_HSTS_PRELOAD', False)
        
        if hsts_seconds == 0:
            self.stdout.write(
                self.style.WARNING('  ⚠️  HSTS not enabled (SECURE_HSTS_SECONDS = 0)')
            )
            return
        
        # Check HSTS duration
        if hsts_seconds < 31536000:  # 1 year
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠️  HSTS duration ({hsts_seconds}s) is less than recommended 1 year'
                )
            )
        else:
            self.stdout.write(f'  ✅ HSTS duration: {hsts_seconds}s')
        
        # Check includeSubDomains
        if include_subdomains:
            self.stdout.write('  ✅ HSTS includeSubDomains enabled')
        else:
            self.stdout.write(
                self.style.WARNING('  ⚠️  Consider enabling HSTS includeSubDomains')
            )
        
        # Check preload
        if preload:
            self.stdout.write('  ✅ HSTS preload enabled')
            if hsts_seconds < 31536000 or not include_subdomains:
                self.stdout.write(
                    self.style.WARNING(
                        '  ⚠️  HSTS preload requires 1+ year duration and includeSubDomains'
                    )
                )
        else:
            self.stdout.write(
                self.style.WARNING('  ⚠️  Consider enabling HSTS preload for better security')
            )

    def check_cors_configuration(self):
        """Check CORS configuration."""
        self.stdout.write('\n🌐 Checking CORS Configuration...')
        
        cors_settings = getattr(settings, 'CORS_SETTINGS', {})
        
        if not cors_settings:
            self.stdout.write('  ℹ️  No CORS configuration found')
            return
        
        allow_all = cors_settings.get('allow_all_origins', False)
        if allow_all:
            self.stdout.write(
                self.style.WARNING('  ⚠️  CORS allows all origins - security risk!')
            )
        else:
            allowed_origins = cors_settings.get('allowed_origins', [])
            if allowed_origins:
                self.stdout.write(f'  ✅ CORS allowed origins: {len(allowed_origins)} configured')
                if self.verbose:
                    for origin in allowed_origins:
                        self.stdout.write(f'    - {origin}')
            else:
                self.stdout.write('  ℹ️  No specific CORS origins configured')
        
        allow_credentials = cors_settings.get('allow_credentials', False)
        if allow_credentials:
            self.stdout.write('  ⚠️  CORS credentials allowed - ensure origins are restricted')
        
        allowed_methods = cors_settings.get('allowed_methods', [])
        if 'DELETE' in allowed_methods or 'PUT' in allowed_methods:
            self.stdout.write('  ⚠️  CORS allows destructive methods - ensure proper authentication')
        
        max_age = cors_settings.get('max_age', 0)
        if max_age > 86400:  # 24 hours
            self.stdout.write(
                self.style.WARNING(f'  ⚠️  CORS max_age ({max_age}s) is quite long')
            )
        elif max_age > 0:
            self.stdout.write(f'  ✅ CORS max_age: {max_age}s')

    def log_message(self, level, message):
        """Log message with appropriate level."""
        if level == 'error':
            logger.error(message)
        elif level == 'warning':
            logger.warning(message)
        else:
            logger.info(message)