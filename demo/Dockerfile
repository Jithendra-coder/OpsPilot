FROM python:3.12-slim

WORKDIR /demo
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
COPY service.py ./service.py
EXPOSE 8081
CMD ["python", "service.py"]
