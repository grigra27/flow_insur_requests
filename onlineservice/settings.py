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
    'onlineservice.middleware.HTTPSSecurityMiddleware',
    'onlineservice.middleware.CSPNonceMiddleware',
    'onlineservice.logging_middleware.SecurityLoggingMiddleware',
    'onlineservice.logging_middleware.PerformanceMonitoringMiddleware',
    'onlineservice.performance_middleware.DatabasePerformanceMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'onlineservice.logging_middleware.FileUploadLoggingMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'insurance_requests.middleware.AuthenticationMiddleware',
    'onlineservice.performance_middleware.QueryCountDebugMiddleware',
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
db_engine = config('DB_ENGINE', default='django.db.backends.sqlite3')

DATABASES = {
    'default': {
        'ENGINE': db_engine,
        'NAME': config('DB_NAME', default=BASE_DIR / 'db.sqlite3'),
        'USER': config('DB_USER', default=''),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default=''),
        'PORT': config('DB_PORT', default=''),
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=300, cast=int),  # 5 minutes connection pooling
        'CONN_HEALTH_CHECKS': True,
    }
}

# Add database-specific optimizations
if 'sqlite' in db_engine:
    DATABASES['default']['OPTIONS'] = {
        'timeout': 20,
    }
elif 'postgresql' in db_engine:
    DATABASES['default']['OPTIONS'] = {
        'connect_timeout': 10,
        'options': '-c default_transaction_isolation=read committed'
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

# Static file optimization settings
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# Static and media files serving configuration for HTTPS
# Use optimized storage with compression and cache busting
if not DEBUG:
    STATICFILES_STORAGE = 'core.static_storage.CompressedManifestStaticFilesStorage'
    # Enable manifest strict mode for better cache busting
    STATICFILES_MANIFEST_STRICT = True
else:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# CDN configuration for static files
STATIC_CDN_URL = config('STATIC_CDN_URL', default='')

# Static file compression settings
STATIC_FILE_COMPRESSION = config('STATIC_FILE_COMPRESSION', default=True, cast=bool)
STATIC_FILE_MINIFICATION = config('STATIC_FILE_MINIFICATION', default=True, cast=bool)

# Cache busting settings
STATIC_FILE_VERSIONING = config('STATIC_FILE_VERSIONING', default=True, cast=bool)
STATIC_FILE_HASH_LENGTH = config('STATIC_FILE_HASH_LENGTH', default=8, cast=int)

# Static file optimization thresholds
STATIC_FILE_COMPRESSION_MIN_SIZE = config('STATIC_FILE_COMPRESSION_MIN_SIZE', default=1024, cast=int)  # 1KB
STATIC_FILE_INLINE_MAX_SIZE = config('STATIC_FILE_INLINE_MAX_SIZE', default=10240, cast=int)  # 10KB

# Preload critical resources
STATIC_PRELOAD_RESOURCES = config(
    'STATIC_PRELOAD_RESOURCES',
    default='css/critical.css,js/critical.js',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

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
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = config('X_FRAME_OPTIONS', default='DENY', cast=str)

# Force security headers even in development if needed
FORCE_SECURITY_HEADERS = config('FORCE_SECURITY_HEADERS', default=False, cast=bool)

# HSTS settings - only enable in production with HTTPS
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)

# Content Security Policy - Base policy
SECURE_CONTENT_SECURITY_POLICY = config(
    'SECURE_CONTENT_SECURITY_POLICY',
    default=(
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https: blob:; "
        "font-src 'self' data: https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "connect-src 'self' https:; "
        "media-src 'self' data: blob:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "upgrade-insecure-requests; "
        "block-all-mixed-content;"
    ),
    cast=str
)

# CSP for admin interface (more permissive)
SECURE_CONTENT_SECURITY_POLICY_ADMIN = config(
    'SECURE_CONTENT_SECURITY_POLICY_ADMIN',
    default=(
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "upgrade-insecure-requests;"
    ),
    cast=str
)

# CSP Report-Only for monitoring violations
SECURE_CONTENT_SECURITY_POLICY_REPORT_ONLY = config(
    'SECURE_CONTENT_SECURITY_POLICY_REPORT_ONLY',
    default='',
    cast=str
)

# HTTPS settings for production
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Additional HTTPS security settings
SECURE_REFERRER_POLICY = config('SECURE_REFERRER_POLICY', default='strict-origin-when-cross-origin', cast=str)
SECURE_CROSS_ORIGIN_OPENER_POLICY = config('SECURE_CROSS_ORIGIN_OPENER_POLICY', default='same-origin', cast=str)
SECURE_CROSS_ORIGIN_EMBEDDER_POLICY = config('SECURE_CROSS_ORIGIN_EMBEDDER_POLICY', default='', cast=str)
SECURE_CROSS_ORIGIN_RESOURCE_POLICY = config('SECURE_CROSS_ORIGIN_RESOURCE_POLICY', default='', cast=str)

# Server header configuration
SECURE_SERVER_HEADER = config('SECURE_SERVER_HEADER', default='', cast=str)

# Paths that should clear site data on access
CLEAR_SITE_DATA_PATHS = config(
    'CLEAR_SITE_DATA_PATHS',
    default='/logout/,/admin/logout/',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

# Permissions Policy configuration
SECURE_PERMISSIONS_POLICY = {
    'geolocation': '()',
    'microphone': '()',
    'camera': '()',
    'payment': '()',
    'usb': '()',
    'magnetometer': '()',
    'gyroscope': '()',
    'accelerometer': '()',
    'ambient-light-sensor': '()',
    'autoplay': '(self)',
    'encrypted-media': '(self)',
    'fullscreen': '(self)',
    'picture-in-picture': '()',
    'screen-wake-lock': '()',
    'web-share': '(self)',
    'clipboard-read': '()',
    'clipboard-write': '(self)',
    'display-capture': '()',
    'document-domain': '()',
    'execution-while-not-rendered': '()',
    'execution-while-out-of-viewport': '()',
    'gamepad': '()',
    'hid': '()',
    'idle-detection': '()',
    'local-fonts': '()',
    'midi': '()',
    'navigation-override': '()',
    'payment': '()',
    'publickey-credentials-get': '()',
    'serial': '()',
    'sync-xhr': '()',
    'window-placement': '()',
    'xr-spatial-tracking': '()',
}

# CORS configuration
CORS_SETTINGS = {
    'allow_all_origins': config('CORS_ALLOW_ALL_ORIGINS', default=False, cast=bool),
    'allowed_origins': config(
        'CORS_ALLOWED_ORIGINS',
        default='',
        cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
    ),
    'allow_credentials': config('CORS_ALLOW_CREDENTIALS', default=False, cast=bool),
    'allowed_methods': config(
        'CORS_ALLOWED_METHODS',
        default='GET,POST,PUT,PATCH,DELETE,HEAD,OPTIONS',
        cast=lambda v: [s.strip() for s in v.split(',')]
    ),
    'allowed_headers': config(
        'CORS_ALLOWED_HEADERS',
        default='Accept,Accept-Language,Content-Language,Content-Type,Authorization,X-CSRFToken,X-Requested-With',
        cast=lambda v: [s.strip() for s in v.split(',')]
    ),
    'expose_headers': config(
        'CORS_EXPOSE_HEADERS',
        default='',
        cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
    ),
    'max_age': config('CORS_MAX_AGE', default=86400, cast=int),
}

# CSRF settings
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='https://onbr.site,https://www.onbr.site', cast=lambda v: [s.strip() for s in v.split(',')])

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
        'detailed': {
            'format': '{levelname} {asctime} {name} {module} {funcName} {lineno} {message}',
            'style': '{',
        },
        'query': {
            'format': '{asctime} [QUERY] {message}',
            'style': '{',
        },
        'security': {
            'format': '{asctime} [SECURITY] {levelname} {module} {message}',
            'style': '{',
        },
        'performance': {
            'format': '{asctime} [PERFORMANCE] {levelname} {message}',
            'style': '{',
        },
        'file_upload': {
            'format': '{asctime} [FILE_UPLOAD] {levelname} {module} {message}',
            'style': '{',
        },
        'json': {
            'format': '{{"timestamp": "{asctime}", "level": "{levelname}", "logger": "{name}", "module": "{module}", "message": "{message}"}}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': ['require_debug_true'],
        },
        'console_production': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'json',
            'filters': ['require_debug_false'],
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'detailed',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 5,
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'errors.log',
            'formatter': 'detailed',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 5,
        },
        'query_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'queries.log',
            'formatter': 'query',
            'maxBytes': 100 * 1024 * 1024,  # 100MB
            'backupCount': 3,
        },
        'performance_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'performance.log',
            'formatter': 'performance',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 5,
        },
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'formatter': 'security',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 10,
        },
        'file_upload_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'file_uploads.log',
            'formatter': 'file_upload',
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 5,
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_debug_false'],
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'console_production', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'console_production', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['error_file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['security_file', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['query_file'] if config('LOG_QUERIES', default=False, cast=bool) else [],
            'level': 'DEBUG',
            'propagate': False,
        },
        'performance': {
            'handlers': ['performance_file', 'console', 'console_production'],
            'level': 'INFO',
            'propagate': False,
        },
        'security': {
            'handlers': ['security_file', 'console', 'console_production'],
            'level': 'WARNING',
            'propagate': False,
        },
        'file_upload': {
            'handlers': ['file_upload_file', 'console', 'console_production'],
            'level': 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'console_production', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'insurance_requests': {
            'handlers': ['console', 'console_production', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'summaries': {
            'handlers': ['console', 'console_production', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Email settings (для будущего использования)
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

# Celery settings (для будущего использования)
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# File upload settings optimized for HTTPS
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB for HTTPS
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB for HTTPS
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755

# Temporary file handling for uploads
FILE_UPLOAD_TEMP_DIR = BASE_DIR / 'media' / 'temp'
os.makedirs(FILE_UPLOAD_TEMP_DIR, exist_ok=True)

# File upload handlers for better performance with large files
FILE_UPLOAD_HANDLERS = [
    'django.core.files.uploadhandler.MemoryFileUploadHandler',
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',
]

# Custom file storage for HTTPS context
class SecureFileSystemStorage:
    """Custom storage class for secure file handling in HTTPS context"""
    
    def __init__(self, location=None, base_url=None):
        from django.core.files.storage import FileSystemStorage
        self._storage = FileSystemStorage(location=location, base_url=base_url)
    
    def __getattr__(self, name):
        return getattr(self._storage, name)
    
    def url(self, name):
        """Ensure URLs are HTTPS in production"""
        url = self._storage.url(name)
        if not DEBUG and not url.startswith('https://'):
            # Force HTTPS for media URLs in production
            if url.startswith('http://'):
                url = url.replace('http://', 'https://', 1)
            elif url.startswith('/'):
                # Relative URL - let nginx handle the protocol
                pass
        return url

# Use secure storage in production
if not DEBUG:
    DEFAULT_FILE_STORAGE = 'onlineservice.settings.SecureFileSystemStorage'
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'


# Database Performance Settings
SLOW_QUERY_THRESHOLD = config('SLOW_QUERY_THRESHOLD', default=0.1, cast=float)  # 100ms
LOG_ALL_QUERIES = config('LOG_ALL_QUERIES', default=False, cast=bool)
LOG_QUERIES = config('LOG_QUERIES', default=False, cast=bool)

# Enhanced Logging Settings
SLOW_REQUEST_THRESHOLD = config('SLOW_REQUEST_THRESHOLD', default=1.0, cast=float)  # 1 second
MEMORY_THRESHOLD = config('MEMORY_THRESHOLD', default=100 * 1024 * 1024, cast=int)  # 100MB
LOG_SECURITY_EVENTS = config('LOG_SECURITY_EVENTS', default=True, cast=bool)
LOG_FILE_UPLOADS = config('LOG_FILE_UPLOADS', default=True, cast=bool)
LOG_PERFORMANCE_METRICS = config('LOG_PERFORMANCE_METRICS', default=True, cast=bool)

# Database connection pooling settings
DB_MAX_CONNS = config('DB_MAX_CONNS', default=20, cast=int)
DB_CONN_MAX_AGE = config('DB_CONN_MAX_AGE', default=300, cast=int)  # 5 minutes

# Query optimization settings
QUERY_CACHE_TIMEOUT = config('QUERY_CACHE_TIMEOUT', default=300, cast=int)  # 5 minutes

# Performance monitoring
ENABLE_PERFORMANCE_MONITORING = config('ENABLE_PERFORMANCE_MONITORING', default=True, cast=bool)

# Cache configuration for query results (if Redis is available)
if config('REDIS_URL', default=''):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': config('REDIS_URL'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 20,
                    'retry_on_timeout': True,
                },
            },
            'KEY_PREFIX': 'insurance_app',
            'TIMEOUT': 300,  # 5 minutes default timeout
        }
    }
    
    # Session backend using Redis for better performance
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    # Fallback to database cache
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'cache_table',
            'TIMEOUT': 300,
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
                'CULL_FREQUENCY': 3,
            }
        }
    }