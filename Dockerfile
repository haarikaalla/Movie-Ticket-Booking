FROM node:22-alpine AS web
WORKDIR /workspace
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install
COPY frontend ./frontend
COPY src ./src
RUN cd frontend && npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BOOKING_DB=/data/bookings.db
WORKDIR /app
RUN addgroup --system booking && adduser --system --ingroup booking booking
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY --from=web /workspace/src/bookmymovie/static ./src/bookmymovie/static
RUN pip install --no-cache-dir . && mkdir -p /data && chown booking:booking /data
USER booking
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "bookmymovie.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
