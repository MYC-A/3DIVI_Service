FROM python:3.12
WORKDIR /app
COPY requirements.txt .

RUN apt-get update && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 80

CMD ["python3", "main.py"]