import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mchangohub.settings')

app = Celery("mchangohub")
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_default_queue = "mchangohub_queue"
app.autodiscover_tasks()