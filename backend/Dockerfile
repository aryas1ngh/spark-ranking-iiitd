FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy backend source
COPY backend/ .

# load_seed_data / load_rankings resolve this by walking up from their own
# file location (see api/management/commands/load_seed_data.py) -- five
# levels up from /app/api/management/commands/ lands on the container's
# filesystem root, so the pipeline's data/ directory has to land at /data
# here to match how that same code resolves ../../../../../data locally.
COPY data/ /data/

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

EXPOSE 8001

ENTRYPOINT ["/app/entrypoint.sh"]
