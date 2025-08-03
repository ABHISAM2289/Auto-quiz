FROM python:3.10-slim

RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and service account key
COPY . .
# This line is optional if gcloud.json is already in the project root (copied by Jenkins)
COPY gcloud.json /app/gcloud.json

# Set the environment variable (this is VERY IMPORTANT!)
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/gcloud.json

CMD ["python", "app.py"]
