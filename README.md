# 3DIVI_Service

[![Python Version](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)  
[![FastAPI](https://img.shields.io/badge/FastAPI-v0.95-blue.svg)](https://fastapi.tiangolo.com/)  
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-13-blue.svg)](https://www.postgresql.org/)  
[![MinIO](https://img.shields.io/badge/MinIO-RELEASED-blue.svg)](https://min.io/)  
[![Celery](https://img.shields.io/badge/Celery-v5-orange.svg)](https://docs.celeryq.dev/en/stable/)  
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-v3.9-blue.svg)](https://www.rabbitmq.com/)

## О проекте

**3DIVI_Service** — это продуктовый сервис для автоматического подсчета числа уникальных клиентов в заведении по фотографиям лиц. Сервис использует передовые технологии компьютерного зрения для детекции и распознавания лиц, позволяя получать точную статистику посещаемости без использования инвазивных методов.

## Архитектура проекта

- **FastAPI Backend**  
  Реализует высокопроизводительный REST API для приема изображений и управления процессом обработки.

- **Celery & RabbitMQ**  
  Организуют асинхронную и отказоустойчивую обработку задач по анализу изображений, обеспечивая масштабируемость и надежность системы.

- **PostgreSQL**  
  Хранит структурированные данные о посетителях и статистику распознавания лиц.

- **MinIO**  
  Используется в качестве объектного хранилища для сохранения загруженных изображений и других бинарных данных.
