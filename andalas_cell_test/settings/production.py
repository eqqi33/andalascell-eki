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
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
