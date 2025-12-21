# Use official lightweight Python image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for Postgres and Pandas
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port 5000 for the internal network
EXPOSE 5000

# Start command: Use Gunicorn for production instead of 'python app.py'
# -w 4: Use 4 worker processes (good for handling multiple users)
# -b: Bind to all interfaces
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]