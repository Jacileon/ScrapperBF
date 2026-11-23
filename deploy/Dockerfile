# ============================================================
# Image PROD légère — sert UNIQUEMENT le front + l'API.
# L'ingestion (OCR/LLM) n'est PAS dans cette image.
# build :  docker build -f deploy/Dockerfile -t veillebf-web .
# run   :  docker run -p 8000:8000 veillebf-web
# ============================================================
FROM python:3.13-slim

WORKDIR /app

# Dépendances runtime seulement
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code + données strictement nécessaires au service
COPY server_front.py .
COPY web/app ./web/app
COPY marches_publics_burkina.db .

EXPOSE 8000
CMD ["uvicorn", "server_front:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
