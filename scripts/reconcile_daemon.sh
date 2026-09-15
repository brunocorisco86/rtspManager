#!/bin/sh
# ==============================================================================
# Reconcile Daemon - Loop de Reconciliação Contínua de CFTV
# ==============================================================================
# Executa a descoberta de MACs, atualização de IPs e hot-reload do go2rtc
# ==============================================================================

INTERVAL="${1:-300}"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Iniciando Daemon de Reconciliação CFTV (Intervalo: ${INTERVAL}s)..."
while true; do
    python3 "$DIR/dynamic_resolver.py"
    sleep "$INTERVAL"
done
