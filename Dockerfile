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

# Copy the application files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the application port
EXPOSE 8080

# Run the application
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]
