<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-blue.svg" alt="Python"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-v0.95-brightgreen.svg" alt="FastAPI"></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-13-red.svg" alt="PostgreSQL"></a>
  <a href="https://min.io/"><img src="https://img.shields.io/badge/MinIO-RELEASED-yellow.svg" alt="MinIO"></a>
  <a href="https://docs.celeryq.dev/en/stable/"><img src="https://img.shields.io/badge/Celery-v5-purple.svg" alt="Celery"></a>
  <a href="https://www.rabbitmq.com/"><img src="https://img.shields.io/badge/RabbitMQ-v3.9-orange.svg" alt="RabbitMQ"></a>
</p>

## О проекте

**3DIVI_Service** — это продуктовый сервис для автоматического подсчета числа уникальных клиентов в заведении по фотографиям лиц. Сервис использует передовые технологии компьютерного зрения для детекции и распознавания лиц, обеспечивая точную статистику посещаемости заведения.

## Архитектура проекта

- **FastAPI Backend**  
  Обеспечивает высокопроизводительный REST API для приема изображений и управления процессом анализа.

- **Celery & RabbitMQ**  
  Организуют асинхронную и отказоустойчивую обработку задач по анализу изображений, что гарантирует масштабируемость и надежность сервиса.

- **PostgreSQL**  
  Хранит структурированные данные о посетителях и статистику распознавания лиц.

- **MinIO**  
  Используется в качестве объектного хранилища для сохранения загруженных изображений и других бинарных данных.
