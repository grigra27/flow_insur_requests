"""
Django settings for onlineservice project.
"""

from pathlib import Path
from decouple import config
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    
    # Local apps
    'insurance_requests',
    'summaries',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'onlineservice.middleware.DomainRoutingMiddleware',  # Domain routing middleware
    'onlineservice.middleware.HTTPSSecurityMiddleware',  # HTTPS security headers middleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'insurance_requests.middleware.AuthenticationMiddleware',
]

ROOT_URLCONF = 'onlineservice.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'onlineservice.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE', default='django.db.backends.sqlite3'),
        'NAME': config('DB_NAME', default=BASE_DIR / 'db.sqlite3'),
        'USER': config('DB_USER', default=''),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default=''),
        'PORT': config('DB_PORT', default=''),

    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication settings
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# Session settings
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = config('SESSION_COOKIE_SAMESITE', default='Lax')

# HTTPS Security settings - Environment controlled
ENABLE_HTTPS = config('ENABLE_HTTPS', default=False, cast=bool)

# SSL Redirect - only enable if HTTPS is enabled
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool) and ENABLE_HTTPS

# HSTS (HTTP Strict Transport Security) settings
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0 if not ENABLE_HTTPS else 31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=ENABLE_HTTPS, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=ENABLE_HTTPS, cast=bool)

# Additional HTTPS security headers
SECURE_REFERRER_POLICY = config('SECURE_REFERRER_POLICY', default='strict-origin-when-cross-origin')
SECURE_CROSS_ORIGIN_OPENER_POLICY = config('SECURE_CROSS_ORIGIN_OPENER_POLICY', default='same-origin')

# Proxy SSL header for reverse proxy setups (Nginx)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if ENABLE_HTTPS else None

# Basic security settings (always enabled)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Additional security headers for HTTPS
if ENABLE_HTTPS:
    # Force HTTPS for admin and other sensitive areas
    SECURE_REDIRECT_EXEMPT = config('SECURE_REDIRECT_EXEMPT', default='', cast=lambda v: [s.strip() for s in v.split(',') if s.strip()])
    
    # SSL certificate validation (for production)
    USE_TLS = True
    
    # Logging for HTTPS-specific events
    HTTPS_LOGGING_ENABLED = config('HTTPS_LOGGING_ENABLED', default=True, cast=bool)
else:
    HTTPS_LOGGING_ENABLED = False

# Configure session and CSRF security based on HTTPS settings
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=ENABLE_HTTPS, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=ENABLE_HTTPS, cast=bool)

# Session and CSRF cookie names for HTTPS
if ENABLE_HTTPS:
    SESSION_COOKIE_NAME = config('SESSION_COOKIE_NAME', default='sessionid_secure')
    CSRF_COOKIE_NAME = config('CSRF_COOKIE_NAME', default='csrftoken_secure')
    
    # CSRF trusted origins configuration
    CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=lambda v: [s.strip() for s in v.split(',') if s.strip()])
    
    # Auto-generate CSRF trusted origins from ALLOWED_HOSTS if not specified
    if not CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS if host not in ['localhost', '127.0.0.1', '*']]
else:
    SESSION_COOKIE_NAME = config('SESSION_COOKIE_NAME', default='sessionid')
    CSRF_COOKIE_NAME = config('CSRF_COOKIE_NAME', default='csrftoken')

# Content Security Policy (basic)
CSP_DEFAULT_SRC = config('CSP_DEFAULT_SRC', default="'self'")
CSP_SCRIPT_SRC = config('CSP_SCRIPT_SRC', default="'self' 'unsafe-inline'")
CSP_STYLE_SRC = config('CSP_STYLE_SRC', default="'self' 'unsafe-inline'")
CSP_IMG_SRC = config('CSP_IMG_SRC', default="'self' data:")
CSP_FONT_SRC = config('CSP_FONT_SRC', default="'self'")
CSP_CONNECT_SRC = config('CSP_CONNECT_SRC', default="'self'")
CSP_FRAME_ANCESTORS = config('CSP_FRAME_ANCESTORS', default="'none'")

# CSRF settings
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = config('CSRF_COOKIE_SAMESITE', default='Lax')

# Logging
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'domain_format': {
            'format': '{levelname} {asctime} [{name}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'multiple_upload_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'multiple_upload.log',
            'formatter': 'verbose',
        },
        'landing_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'landing.log',
            'formatter': 'domain_format',
        },
        'domain_routing_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'domain_routing.log',
            'formatter': 'domain_format',
        },
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'formatter': 'verbose',
        },
        'https_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'https.log',
            'formatter': 'domain_format',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'security_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'summaries.excel_export': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'summaries.services.multiple_file_processor': {
            'handlers': ['console', 'file', 'multiple_upload_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'onlineservice.middleware': {
            'handlers': ['console', 'domain_routing_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'onlineservice.views': {
            'handlers': ['console', 'landing_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security.csrf': {
            'handlers': ['console', 'security_file', 'https_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'security_file', 'https_file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Excel export settings
SUMMARY_TEMPLATE_PATH = BASE_DIR / 'templates' / 'summary_template.xlsx'

# Domain configuration for multi-domain support
MAIN_DOMAINS = config('MAIN_DOMAINS', default='insflow.tw1.su', cast=lambda v: [s.strip() for s in v.split(',')])
SUBDOMAINS = config('SUBDOMAINS', default='zs.insflow.tw1.su', cast=lambda v: [s.strip() for s in v.split(',')])

# All supported domains (for validation and logging)
ALL_SUPPORTED_DOMAINS = MAIN_DOMAINS + SUBDOMAINS

# Development domains
DEVELOPMENT_DOMAINS = ['localhost', '127.0.0.1', 'testserver']

