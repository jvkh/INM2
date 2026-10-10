FROM python:3.12-slim

WORKDIR /app

COPY collector/requirements.txt ./collector/requirements.txt
RUN pip install --no-cache-dir -r collector/requirements.txt

COPY common ./common
COPY collector ./collector

CMD ["python", "-m", "collector.main"]
