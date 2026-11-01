# JD ↔ Resume Match Scorer — Apify Actor
# Build context is the repo root (see dockerContextDir in .actor/actor.json)
FROM apify/actor-python:3.11

# tesseract-ocr + poppler-utils: OCR fallback for scanned PDFs (pytesseract, pdf2image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY execution/ ./execution/
COPY actors/jd-match-scorer/ ./actors/jd-match-scorer/

CMD ["python", "actors/jd-match-scorer/main.py"]
