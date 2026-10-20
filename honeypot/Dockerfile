FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --chown=65532:65532 honeypot/main.py ./main.py
COPY --chown=65532:65532 honeypot/assets ./assets
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["python", "/app/main.py"]
