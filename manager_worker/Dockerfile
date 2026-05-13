FROM python:3.11

WORKDIR /app

RUN pip install minio

COPY worker.py .

CMD ["python", "worker.py"]