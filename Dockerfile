# Use the official Python base image
FROM python:3.10-slim

# Install required system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libmariadb-dev-compat \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files, including .env
COPY . /app

# Expose the application port
EXPOSE 8080

# Run the application with gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]

