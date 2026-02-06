# Multi-stage build for MCProxy
# Stage 1: Build dependencies
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Production image
FROM python:3.11-slim

# Create non-root user for security
RUN groupadd -r mcproxy && useradd -r -g mcproxy mcproxy

# Set working directory
WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /root/.local /home/mcproxy/.local
ENV PATH=/home/mcproxy/.local/bin:$PATH

# Copy application code
COPY --chown=mcproxy:mcproxy *.py .

# Create config directory
RUN mkdir -p /app/config && chown -R mcproxy:mcproxy /app

# Switch to non-root user
USER mcproxy

# Expose the SSE endpoint port
EXPOSE 12009

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:12009/sse', timeout=5)" || exit 1

# Run MCProxy
ENTRYPOINT ["python", "main.py"]
CMD ["--log", "--config", "/app/config/mcp-servers.json"]
