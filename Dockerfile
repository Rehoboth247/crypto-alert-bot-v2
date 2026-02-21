# Use Python with Chrome for Selenium
FROM python:3.11-slim

# Install Chromium and dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# ChromeDriver is managed automatically by webdriver-manager at runtime

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create data directory for persistent volume
RUN mkdir -p /app/data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/data/tokens.db
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null
ENV CHROME_FLAGS="--disable-dev-shm-usage --no-sandbox"

# Command to run the bot
CMD ["python", "main.py"]
