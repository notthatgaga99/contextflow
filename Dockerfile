# Non-root Cloud Run image for ContextFlow POC.
FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY . .
RUN chown -R appuser:appuser /srv

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
# Default MockLLM. Vertex uses ADC / workload identity — no keys in image.
USER 10001

# uvicorn handles SIGTERM for graceful drain (Cloud Run timeoutSeconds).
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
