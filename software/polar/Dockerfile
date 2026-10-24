FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY polar_core ./polar_core
COPY static ./static
ENV POLAR_DATA_DIR=/data PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home polar && mkdir /data && chown polar:polar /data
USER polar
VOLUME /data
EXPOSE 8765
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8765", "--timeout", "180", "app:create_app()"]
