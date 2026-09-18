FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-dejavu-core \
        libgl1 \
        libglib2.0-0 \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY requirements.txt requirements-rdocs.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-rdocs.txt \
    && pip install --no-cache-dir --no-deps "git+https://github.com/protei300/RussianDocsOCR.git@v4.4.1" \
    && rdocs-fetch-models

COPY app ./app
COPY templates_docx ./templates_docx

CMD ["python", "-m", "app.main"]