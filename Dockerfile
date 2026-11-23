# 1) Interface web (React + Vite)
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

# 2) API + núcleo Quantum, servindo a interface na raiz
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[api]"
COPY --from=web /web/dist ./web/dist
ENV QUANTUM_PASTA_ARQUIVOS=/dados/arquivos \
    QUANTUM_DATABASE_URL=sqlite:////dados/quantum.db \
    QUANTUM_PASTA_WEB=/app/web/dist
VOLUME /dados
EXPOSE 8000
CMD ["sh", "-c", "uvicorn quantum_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
