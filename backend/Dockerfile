FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN useradd --uid 1000 --create-home app && mkdir -p /app/data/media && chown -R app:app /app
USER app
