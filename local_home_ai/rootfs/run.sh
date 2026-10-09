#!/command/with-contenv bashio
# ==============================================================================
# Local Home AI entrypoint
# ==============================================================================
set -euo pipefail

bashio::log.info "Starting Local Home AI..."

export LHAI_OPTIONS_PATH="/data/options.json"
export LHAI_DATA_DIR="/data"
export LHAI_SHARE_DIR="/share/local_home_ai"

mkdir -p "${LHAI_DATA_DIR}" "${LHAI_SHARE_DIR}"

# Supervisor writes options to /data/options.json automatically.
if [[ ! -f "${LHAI_OPTIONS_PATH}" ]]; then
  bashio::log.warning "options.json missing; creating empty object"
  echo '{}' > "${LHAI_OPTIONS_PATH}"
fi

# Expose bundled custom component for copy into /config/custom_components
if [[ -d /opt/local_home_ai/custom_components ]]; then
  mkdir -p "${LHAI_SHARE_DIR}/custom_components"
  cp -a /opt/local_home_ai/custom_components/. "${LHAI_SHARE_DIR}/custom_components/" || true
  bashio::log.info "Synced custom_components to ${LHAI_SHARE_DIR}/custom_components"
fi

export PYTHONPATH="/opt/local_home_ai"
cd /opt/local_home_ai
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8099
