FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY db.py .
COPY tools.py .
COPY security.py .
COPY observability.py .
COPY request_controls.py .
COPY idempotency.py .
COPY recover_idempotency.py .
COPY agent_skills ./agent_skills

EXPOSE 8000

CMD ["sh", "-c", "python recover_idempotency.py && exec uvicorn app:app --host 0.0.0.0 --port 8000"]
