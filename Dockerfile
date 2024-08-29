# --- Build Stage ---
# Use the official lightweight Python image.
FROM python:3.10-slim AS builder

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Create and change to the app directory
WORKDIR /usr/src/app

# Copy application dependency manifests to the container image
COPY requirements.txt ./

# Upgrade pip and install dependencies to a local user directory
RUN pip install --upgrade pip && pip install --no-cache-dir --user -r requirements.txt

# --- Final Stage ---
# Use a new lightweight Python image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"
ENV PORT 8080

# Create and change to the app directory
WORKDIR /usr/src/app

# Copy only the necessary files from the builder stage
COPY --from=builder /root/.local /root/.local
COPY . ./

# Run the web service on container startup using Gunicorn or Uvicorn
# Choose between Gunicorn or Uvicorn below:

# Option 1: Using Gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app

# Option 2: Using Uvicorn (Uncomment the line below if you prefer Uvicorn)
# CMD exec uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 0

