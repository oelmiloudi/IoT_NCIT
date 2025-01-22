# using the official Python base image
FROM python:3.10-slim

# install required system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libmariadb-dev-compat \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

# set the working directory
WORKDIR /app

# copy the application files
COPY . .

# install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# expose the application port
EXPOSE 8080

# run the application
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]
