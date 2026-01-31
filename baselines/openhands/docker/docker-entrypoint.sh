#!/bin/bash
set -e

# --------------------------------------------------------------------------- #
# Detect cluster paths
# --------------------------------------------------------------------------- #
PG_VERSION="$(ls /etc/postgresql | sort -V | tail -n1)"
PG_CONF_DIR="/etc/postgresql/${PG_VERSION}/main"
PG_DATA_DIR="/var/lib/postgresql/${PG_VERSION}/main"
PG_CONF="${PG_CONF_DIR}/postgresql.conf"
PG_HBA="${PG_CONF_DIR}/pg_hba.conf"

echo "[DOCKER] Detected PostgreSQL $PG_VERSION"
echo "[DOCKER]   conf  dir: $PG_CONF_DIR"
echo "[DOCKER]   data dir: $PG_DATA_DIR"

# --------------------------------------------------------------------------- #
# 1. Ensure both config & data directories have the *same* owner
# --------------------------------------------------------------------------- #
owner_uid="$(stat -c %u "$PG_CONF_DIR")"
owner_gid="$(stat -c %g "$PG_CONF_DIR")"

fix_owner() {
  local dir="$1"
  if [ "$(stat -c %u "$dir")" != "$owner_uid" ] ||
     [ "$(stat -c %g "$dir")" != "$owner_gid" ]; then
    echo "[DOCKER] Fixing ownership of $dir to ${owner_uid}:${owner_gid} ..."
    chown -R "${owner_uid}:${owner_gid}" "$dir"
  fi
}
fix_owner "$PG_CONF_DIR"
fix_owner "$PG_DATA_DIR"

# --------------------------------------------------------------------------- #
# 2. Create cluster if the bind-mounted directory is empty
# --------------------------------------------------------------------------- #
if [ ! -f "${PG_DATA_DIR}/PG_VERSION" ]; then
  echo "[DOCKER] Initialising new cluster in ${PG_DATA_DIR} ..."
  su postgres -c "/usr/lib/postgresql/${PG_VERSION}/bin/initdb -D '${PG_DATA_DIR}' \
        --username=postgres --encoding=UTF8 --locale=C"
fi

# --------------------------------------------------------------------------- #
# 3. Basic configuration tweaks
# --------------------------------------------------------------------------- #
sed -ri "s/^#?listen_addresses\s*=.*/listen_addresses = '*'/" "$PG_CONF"
grep -q 'host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+0\.0\.0\.0/0' "$PG_HBA" \
  || echo "host all all 0.0.0.0/0 md5" >> "$PG_HBA"
grep -q 'host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+::/0' "$PG_HBA" \
  || echo "host all all ::/0 md5"      >> "$PG_HBA"

# --------------------------------------------------------------------------- #
# 4. Start PostgreSQL
# --------------------------------------------------------------------------- #
service postgresql start

# --------------------------------------------------------------------------- #
# 5. (Optional) create user / database once the server is up
# --------------------------------------------------------------------------- #
sleep 5
create_role() {
  su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='$1'\"" | grep -q 1 ||
    su postgres -c "psql -c \"CREATE USER $1 WITH SUPERUSER PASSWORD '$2';\""
}
create_db() {
  su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$1'\"" | grep -q 1 ||
    su postgres -c "createdb -O $2 $1"
}

[ -n "$POSTGRES_USER" -a -n "$POSTGRES_PASSWORD" ] && create_role "$POSTGRES_USER" "$POSTGRES_PASSWORD"
[ -n "$POSTGRES_DB"   -a -n "$POSTGRES_USER"     ] && create_db   "$POSTGRES_DB"   "$POSTGRES_USER"

# --------------------------------------------------------------------------- #
# 6. Hand control to OpenHands or whatever CMD the user supplied
# --------------------------------------------------------------------------- #
SERVER_BIN="/usr/local/bin/openhands-agent-server"
if [ $# -eq 0 ] || [[ "$1" == "-"* ]]; then
  set -- "$SERVER_BIN" "$@"
fi
exec "$@"
