FROM postgres:16-bookworm

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    tzdata \
  && rm -rf /var/lib/apt/lists/*

ENV TZ=America/Sao_Paulo
ENV PGCONNECT_TIMEOUT=10
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN python3 -m venv /opt/venv \
  && pip install --no-cache-dir \
    apscheduler==3.10.4 \
    fastapi==0.115.6 \
    jinja2==3.1.5 \
    psycopg[binary]==3.2.3 \
    reportlab==4.2.5 \
    uvicorn[standard]==0.34.0

WORKDIR /app

COPY app /app/app

CMD ["python", "-m", "app.main"]
