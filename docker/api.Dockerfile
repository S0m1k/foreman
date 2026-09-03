FROM python:3.12-slim

WORKDIR /app

# fonts so evidence crops of Cyrillic documents render correctly
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY prompts ./prompts

RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "dc_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
