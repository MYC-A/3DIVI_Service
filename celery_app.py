from celery import Celery

# Настроим Celery с использованием RabbitMQ в качестве брокера
app = Celery('tasks', broker="pyamqp://guest:guest@localhost//")

