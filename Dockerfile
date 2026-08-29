FROM python:3.12-slim

# Install pinned dependencies first, so this layer is cached.
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the tool itself.
COPY src/coolify_cf_tunnel_sync /app/coolify_cf_tunnel_sync

# Run as a normal user, not root.
# The tool only writes one file: /tmp/last_sync_ok (used by the healthcheck).
RUN useradd --system --uid 10001 --no-create-home appuser
USER appuser

# Healthy = a sync finished OK recently.
# The tool touches /tmp/last_sync_ok after every successful cycle.
# If the file is missing or older than 2 poll cycles, the check fails.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import os,sys,time; age=time.time()-os.path.getmtime('/tmp/last_sync_ok'); sys.exit(0 if age < 2*float(os.environ.get('POLL_INTERVAL','120')) else 1)"

ENTRYPOINT ["python", "-m", "coolify_cf_tunnel_sync"]
