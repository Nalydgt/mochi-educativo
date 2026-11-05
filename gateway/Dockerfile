FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY *.py ./
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
ENV MOCHI_DATA_DIR=/data
EXPOSE 8765
CMD ["uvicorn", "app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8765"]
