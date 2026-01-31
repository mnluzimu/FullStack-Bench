# ──────────────────────────────────────────────────────────────
# Image based on the one that already runs as the "openhands" user
# ──────────────────────────────────────────────────────────────
FROM ghcr.io/openhands/agent-server:latest-python

# 1) Become root just for the package installation
USER root

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      postgresql postgresql-contrib \
 && rm -rf /var/lib/apt/lists/*

# 2) Return to the non-privileged account declared in the base image
# USER openhands

# 3) Copy and prepare your entry-point script         (still as openhands)
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 4) Runtime configuration
#    (set these at run-time instead of baking them into the image if possible)
ENV POSTGRES_DB=myapp \
    POSTGRES_USER=myappuser \
    POSTGRES_PASSWORD=myapppassword

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
