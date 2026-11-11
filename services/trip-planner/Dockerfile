FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS builder
WORKDIR /build
COPY app.py metrics.py ./

FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get upgrade --yes && rm -rf /var/lib/apt/lists/*
COPY --from=builder --chown=65534:65534 /build/ ./
USER 65534:65534
EXPOSE 8080
CMD ["python", "app.py"]
