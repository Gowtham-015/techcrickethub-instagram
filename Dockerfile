FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    INSTAGRAM_DRY_RUN=true \
    INSTAGRAM_AUTOMATION_ENABLED=true \
    INSTAGRAM_SCHEDULER_ENABLED=true

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create persistent data directory
RUN mkdir -p /app/data

# Run continuous Instagram automation engine
CMD ["python", "main.py", "--run"]
