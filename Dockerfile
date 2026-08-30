FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
# Default MockLLM. Set CF_USE_GEMINI=1 + ADC/Secret Manager for Vertex.
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
