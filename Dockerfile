# Backend image for Render / Railway. Build from the repository root.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt requirements-ai.txt ./
RUN pip install --no-cache-dir -r requirements-ai.txt
COPY backend ./backend
COPY ai ./ai
COPY data ./data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
