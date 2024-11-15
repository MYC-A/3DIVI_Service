from celery import Celery
import task

# ======================================================================================================================
# Запуск RabbitMQ: sudo systemctl start rabbitmq-server
# Запуск celery  : celery -A celery_app worker --loglevel=info
# ======================================================================================================================




# Настроим Celery с использованием RabbitMQ в качестве брокера
app = Celery('tasks', broker="pyamqp://guest:guest@localhost//")

