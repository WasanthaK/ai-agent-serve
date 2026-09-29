FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY runtime.py .
COPY db.py .
COPY tools.py .
COPY security.py .
COPY observability.py .
COPY operational_metrics.py .
COPY request_controls.py .
COPY idempotency.py .
COPY recover_idempotency.py .
COPY inbound.py .
COPY inbound_adapters.py .
COPY inbound_persistence.py .
COPY sendgrid_inbound.py .
COPY sendgrid_routes.py .
COPY twilio_whatsapp.py .
COPY twilio_whatsapp_routes.py .
COPY agent_skills ./agent_skills

EXPOSE 8000

CMD ["sh", "-c", "python recover_idempotency.py && exec uvicorn runtime:app --host 0.0.0.0 --port 8000"]
