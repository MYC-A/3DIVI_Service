FROM python:3.12-slim

WORKDIR /app

RUN echo "deb https://deb.debian.org/debian bookworm main" > /etc/apt/sources.list && \
    echo "deb https://deb.debian.org/debian bookworm-updates main" >> /etc/apt/sources.list && \
    echo "deb https://security.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list

RUN apt-get update -o Acquire::AllowInsecureRepositories=true && \
    apt-get install -y --allow-unauthenticated \
        ca-certificates \
        gnupg2 \
        curl && \
    apt-key adv --refresh-keys --keyserver keyserver.ubuntu.com && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN apt-get update || true

COPY . .

COPY docker_requirements.txt .
RUN pip install --no-cache-dir -r docker_requirements.txt


EXPOSE 80

CMD ["python3", "main.py"]