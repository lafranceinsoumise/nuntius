"""
We test that having another celery app in the project does not conflict
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "standalone.settings")
