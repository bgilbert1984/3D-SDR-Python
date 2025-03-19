# Use CUDA-enabled base image to support ML operations
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# Set working directory
WORKDIR /app

# Install system dependencies, Python and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-dev \
    build-essential \
    git \
    librtlsdr-dev \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app/

# Install Python dependencies including FastAPI and uvicorn
RUN pip3 install --no-cache-dir -r requirements.txt fastapi uvicorn

# Install Node.js dependencies
RUN cd backend && npm install

# Expose ports (adjust if needed based on your application)
EXPOSE 8000

# Set Python path
ENV PYTHONPATH=/app

# Command to run the FastAPI application with uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]