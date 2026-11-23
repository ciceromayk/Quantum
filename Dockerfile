FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[api]"
ENV QUANTUM_PASTA_ARQUIVOS=/dados/arquivos \
    QUANTUM_DATABASE_URL=sqlite:////dados/quantum.db
VOLUME /dados
EXPOSE 8000
CMD ["sh", "-c", "uvicorn quantum_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
