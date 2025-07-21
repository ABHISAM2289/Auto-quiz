FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app code
COPY . .

# Expose your Flask port (e.g., 5001 for speech-to-text)
EXPOSE 5001

# Run your app
CMD ["python", "app.py"]