FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPSPILOT_DATA_DIR=/data \
    OPSPILOT_HOST=0.0.0.0 \
    OPSPILOT_PORT=8765

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt \
    && useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin opspilot \
    && mkdir /data \
    && chown opspilot:opspilot /data

COPY --chown=opspilot:opspilot app.py ./
COPY --chown=opspilot:opspilot backend/ ./backend/
COPY --chown=opspilot:opspilot scripts/ ./scripts/
COPY --chown=opspilot:opspilot web/ ./web/

USER 10001:10001
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import json,urllib.request;d=json.load(urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health',timeout=2));assert d.get('status')=='ok' and d.get('database')=='ready'"
ENTRYPOINT ["python", "app.py"]
