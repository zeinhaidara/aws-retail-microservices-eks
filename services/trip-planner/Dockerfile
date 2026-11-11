FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=65534:65534 app.py metrics.py ./
USER 65534:65534
EXPOSE 8080
CMD ["python", "app.py"]
