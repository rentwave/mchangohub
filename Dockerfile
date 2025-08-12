FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

RUN apt update && apt install -y --no-install-recommends \
    g++ libpq-dev gcc musl-dev libssl-dev libffi-dev && \
    apt clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

EXPOSE 8055

RUN apt remove -y --purge gcc g++ && apt autoremove -y

RUN mkdir -p /var/www/mchangohub

CMD ["./run.sh"]