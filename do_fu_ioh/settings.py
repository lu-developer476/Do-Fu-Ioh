import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() == 'true'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-secret-key-change-me')
if not DEBUG and SECRET_KEY == 'dev-secret-key-change-me':
    raise RuntimeError('DJANGO_SECRET_KEY must be configured when DEBUG=False')


def _split_env_list(value):
    return [item.strip() for item in value.split(',') if item.strip()]


def _sanitize_env_value(raw_value, env_key):
    value = (raw_value or '').strip().strip('"').strip("'")
    prefix = f'{env_key}='
    if value.startswith(prefix):
        return value[len(prefix):].strip().strip('"').strip("'")
    return value


def _merge_unique(*groups):
    merged = []
    for group in groups:
        for item in group:
            if item not in merged:
                merged.append(item)
    return merged


ALLOWED_HOSTS = _merge_unique(
    _split_env_list(_sanitize_env_value(os.getenv('DJANGO_ALLOWED_HOSTS', ''), 'DJANGO_ALLOWED_HOSTS')),
    ['do-fu-ioh.onrender.com', '127.0.0.1', 'localhost'],
)

CSRF_TRUSTED_ORIGINS = _split_env_list(_sanitize_env_value(os.getenv(
    'CSRF_TRUSTED_ORIGINS',
    'https://do-fu-ioh.onrender.com,http://127.0.0.1:8000,http://localhost:8000',
), 'CSRF_TRUSTED_ORIGINS'))

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'do_fu_ioh.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'core' / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'do_fu_ioh.wsgi.application'

DATABASE_URL = _sanitize_env_value(os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR}/db.sqlite3'), 'DATABASE_URL')
DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=DATABASE_URL.startswith('postgres'))
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / '.staticfiles'
STATICFILES_STORAGE = (
    'django.contrib.staticfiles.storage.StaticFilesStorage'
    if DEBUG
    else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
)
STATICFILES_DIRS = [BASE_DIR / 'public']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = os.getenv('DJANGO_SECURE_SSL_REDIRECT', str(not DEBUG)).lower() == 'true'
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.security.DisallowedHost': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
