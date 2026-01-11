"""Development settings.

Use via:
  export DJANGO_SETTINGS_MODULE=andalas_cell_test.settings.development
"""

from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
