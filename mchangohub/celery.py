import os
from celery import Celery
from celery.schedules import schedule  # for fine-grained seconds-based intervals

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mchangohub.settings')

app = Celery("mchangohub")
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_default_queue = "mchangohub_queue"
app.conf.timezone = "Africa/Nairobi"
app.conf.enable_utc = True
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'check-topup-status-every-5-seconds': {
        'task': 'billing.tasks.check_topup_status',  # full path to your Celery task
        'schedule': schedule(run_every=5.0),         # every 5 seconds
    },
    'check-payment-status-every-5-seconds': {
        'task': 'billing.tasks.check_payment_status', # full path to your Celery task
        'schedule': schedule(run_every=5.0),          # every 5 seconds
    },
}
