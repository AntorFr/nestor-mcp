FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISABLE_AUTOUPDATER=1
ENV HOME=/tmp
ENV XDG_CACHE_HOME=/tmp/.cache
ENV XDG_CONFIG_HOME=/tmp/.config
ENV FASTEMBED_CACHE_PATH=/app/.cache/fastembed
ENV HA_RETRIEVAL_EMBEDDING_MODEL=intfloat/multilingual-e5-small

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        nodejs \
        npm \
        ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir ".[embeddings]"

# Pre-download retrieval embedding model into the image so first request is fast
# and the model survives container restarts (HOME=/tmp is ephemeral).
RUN mkdir -p "${FASTEMBED_CACHE_PATH}" \
    && python -c "from fastembed import TextEmbedding; m = TextEmbedding(model_name='${HA_RETRIEVAL_EMBEDDING_MODEL}'); list(m.embed(['warmup']))"

EXPOSE 8000

CMD ["python", "-m", "nestor_mcp.server"]
