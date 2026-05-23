FROM python:3.10-slim

# Create a non-root user
RUN groupadd -r aegis && useradd -r -g aegis aegis

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . /app

# Set proper ownership
RUN chown -R aegis:aegis /app

# Switch to non-root user
USER aegis

# Expose port
EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
