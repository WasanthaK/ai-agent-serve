FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Keep the runtime image aligned with the repository's root Python modules.
# Earlier explicit COPY entries silently excluded later Phase 5-7 modules.
COPY *.py ./
COPY agent_skills ./agent_skills

EXPOSE 8000

CMD ["sh", "-c", "python recover_idempotency.py && exec uvicorn runtime:app --host 0.0.0.0 --port 8000"]
