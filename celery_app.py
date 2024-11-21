from celery import Celery
from celery.schedules import crontab
import task
# ======================================================================================================================
# Запуск RabbitMQ    : sudo systemctl start rabbitmq-server
# Запуск celery      : celery -A celery_app worker --loglevel=info
# Запуск celery beat : celery -A celery_app beat --loglevel=info
# ======================================================================================================================




# Настроим Celery с использованием RabbitMQ в качестве брокера
app = Celery('tasks', broker="pyamqp://guest:guest@localhost//")

app.conf.beat_schedule = {
    'controller': {
        'task': 'task.controller',
        'schedule': crontab(minute='*/1'),},}
