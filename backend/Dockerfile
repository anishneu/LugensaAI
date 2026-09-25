# The Lugensa AI backend. Ollama is NOT in this image: the model runs on the host and the container reaches it over the network
# (see docker-compose.yml). No API key is baked in either: keys are passed at run time.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EVIDENCE_DB_PATH=/app/data/evidence.db

WORKDIR /app

# CPU-only PyTorch first: the default wheel pulls the CUDA build, which is about 2 GB and useless without a GPU.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Run as an ordinary user. /app/data holds the per-run evidence store; ~/.cache holds the embedding model and ~/.local/share the
# translation packs, both of which download on first use and are kept in volumes (see docker-compose.yml).
RUN useradd --create-home --uid 1000 lugensa \
    && mkdir -p /app/data /home/lugensa/.cache /home/lugensa/.local/share \
    && chown -R lugensa:lugensa /app /home/lugensa
USER lugensa

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
