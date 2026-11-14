FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh","-ec","alembic upgrade head && python -m sentrix.seed && exec uvicorn sentrix.api:app --host 0.0.0.0"]
