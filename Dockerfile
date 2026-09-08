FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --system --create-home appuser
USER appuser

# Cloud Run injects PORT; gunicorn binds to it below.
ENV PORT=8080
EXPOSE 8080

# --timeout 120: the "Research all with AI" bulk action makes up to 15
# sequential Gemini calls in one request, which can run past gunicorn's
# 30s default worker timeout.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 120 wsgi:app"]
