FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p custom_parsers uploads outputs data
RUN touch custom_parsers/__init__.py

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Hardcoded port - NO VARIABLES
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
