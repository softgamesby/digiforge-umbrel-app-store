# DigiForge web image — Developed by Mikal
FROM python:3.12-alpine@sha256:1887c114801a8c82a4ec01daa52cfe7fc3f63573640e2247320289807ac1c3bb

WORKDIR /app

RUN pip install --no-cache-dir "pg8000==1.31.5"

COPY web/server.py /app/server.py
COPY web/index.html /app/index.html
COPY web/icon.svg /app/icon.svg
COPY web/init-secrets.py /app/init-secrets.py
COPY config/config.default.json /app/config.default.json

CMD ["python", "/app/server.py"]
