# Small Python base image. Build it for linux/amd64 (x86_64), the CPU type of
# the Fargate tasks that run it (the task definition asks for X86_64).
FROM python:3.12-slim

# Print logs straight away; don't write .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first: this layer is rebuilt only when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the service and the three model files it loads at start-up.
COPY fastapi_app.py .
COPY artifacts/ artifacts/

# Run as an unprivileged user; the service only needs port 8000.
USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "fastapi_app:app", "--host", "0.0.0.0", "--port", "8000"]
