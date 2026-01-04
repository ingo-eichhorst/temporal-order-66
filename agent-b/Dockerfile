FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Expose HTTP port
EXPOSE 8080

# Run both worker and server concurrently
# When crash happens (sys.exit(1) in crash_worker activity), both processes die
# Docker will restart the container per restart: unless-stopped policy
CMD ["sh", "-c", "python -m src.worker & python -m uvicorn src.server:app --host 0.0.0.0 --port 8080 & wait"]
