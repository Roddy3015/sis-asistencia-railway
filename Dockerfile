FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .


CMD ["sh", "-c", "echo \"PORT=$PORT\"; gunicorn -b 0.0.0.0:${PORT:-8080} app:app --workers=2 --threads=4 --timeout=120 --log-level=debug --access-logfile - --error-logfile - --capture-output"]

