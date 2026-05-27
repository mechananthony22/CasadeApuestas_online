FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    postgresql-client \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements/base.txt requirements/dev.txt /tmp/
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/dev.txt

# Copy project files
COPY . /app/

# Expose Django/Daphne port
EXPOSE 8000

# Command will be overridden in docker-compose
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
