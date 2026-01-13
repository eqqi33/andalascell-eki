"""Production settings.

Use via:
  export DJANGO_SETTINGS_MODULE=andalas_cell_test.settings.production

This module enforces that a real secret key is provided.
"""

import os

from .base import *
from .base import _env_csv

DEBUG = False

# In production, require a secret key from the environment.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ALLOWED_HOSTS = _env_csv("DJANGO_ALLOWED_HOSTS", default=[])

# Security best-practices (minimal)
CSRF_COOKIE_SECURE = True  # Wajib jika pakai HTTPS
SESSION_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = [
    'https://andalascell-eki-production.up.railway.app/',
    'https://*.railway.app'
]
CSRF_FAILURE_VIEW = 'django.views.csrf.csrf_failure'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
