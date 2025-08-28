# Use official Python image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements if exists, else install manually
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir python-dotenv python-telegram-bot requests

# Copy bot code
COPY bot.py ./

# Set environment variables (override in production)
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "bot.py"]

EXPOSE 8000
