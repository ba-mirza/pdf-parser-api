FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py .
COPY parser.py .
COPY excel_parser.py .
COPY excel_export.py .
COPY hybrid_compare.py .

RUN mkdir -p /tmp

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE ${PORT}

CMD uvicorn api:app --host 0.0.0.0 --port ${PORT}
