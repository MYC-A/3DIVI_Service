from celery import Celery
from celery.schedules import crontab
from kombu import Queue
import task
# ======================================================================================================================
# Запуск RabbitMQ    : sudo systemctl start rabbitmq-server
# Запуск celery      : celery -A celery_app worker --loglevel=info
# Запуск celery beat : celery -A celery_app beat --loglevel=info
# celery -A celery_app worker --loglevel=info --queues=queue_detection --concurrency=8
# celery -A celery_app worker --loglevel=info --queues=queue_template --concurrency=3
# celery -A celery_app worker --loglevel=info --queues=queue_quality --concurrency=2
# celery -A celery_app worker --loglevel=info --queues=queue_controller --concurrency=1
#
# =============================================
# MINIO DOCKER :
# docker run -d --name minio -p 9000:9000 -p 9090:9090 -e "MINIO_ROOT_USER=minioadmin" -e "MINIO_ROOT_PASSWORD=minioadmin" quay.io/minio/minio server /data --console-address ":9090"
# =============================================
#
# ======================================================================================================================




# Настроим Celery с использованием RabbitMQ в качестве брокера
app = Celery('tasks', broker="pyamqp://guest:guest@localhost//")

app.conf.beat_schedule = {
    'controller': {
        'task': 'task.controller.controller',
        'schedule': crontab(minute='*/1'),
        'options': {'queue': 'queue_controller'}
    },
}

app.conf.task_queues = (
    Queue('queue_detection'),
    Queue('queue_template'),
    Queue('queue_quality'),
    Queue('queue_controller'),
)


app.conf.task_routes = {
    'tasks.detection.*': {'queue': 'queue_detection'},
    'tasks.template.*': {'queue': 'queue_template'},
    'tasks.quality.*': {'queue': 'queue_quality'},
    'tasks.controller*': {'queue': 'queue_controller'},
}