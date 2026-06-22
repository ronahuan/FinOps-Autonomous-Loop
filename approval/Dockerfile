FROM python:3.11-slim
WORKDIR /app
COPY server.py .
RUN pip install --no-cache-dir httpx python-dotenv
CMD ["python", "server.py"]
