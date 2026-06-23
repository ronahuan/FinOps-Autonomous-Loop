FROM python:3.11-slim

WORKDIR /app/observer

COPY pyproject.toml .
COPY observer/ observer/
COPY tests/fixtures/ tests/fixtures/

RUN pip install --no-cache-dir . && mkdir -p /app/observer/out/proposals && chmod -R 777 /app/observer/out

CMD ["python", "-m", "observer.main"]
