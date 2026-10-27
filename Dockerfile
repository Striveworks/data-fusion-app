FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY chariot_client-0.27.3-py3-none-any.whl .
RUN pip install --no-cache-dir ./chariot_client-0.27.3-py3-none-any.whl

COPY app ./app
COPY forge ./forge
COPY scripts ./scripts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
