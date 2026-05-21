FROM python:3.12-slim

# Tesseract OCR + 中英文语言包
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-chi-tra \
    tesseract-ocr-eng \
    wget \
    && rm -rf /var/lib/apt/lists/*

# LibreOffice（用于 .doc → .docx 转换）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
