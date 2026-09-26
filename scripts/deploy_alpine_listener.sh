#!/bin/sh
# ==============================================================================
# deploy_alpine_listener.sh - Implantação do Daemon de Eventos e Relatório
# no nó Alpine (192.168.1.7) onde o pendrive cinza está montado.
# ==============================================================================

set -e

ALPINE_HOST="alpine"
TARGET_DIR="/usr/local/bin"
SERVICE_NAME="cftv-events"

echo "🚀 Iniciando deploy no nó Alpine ($ALPINE_HOST)..."

# 1. Garante que os diretórios existem no pendrive
ssh $ALPINE_HOST "mkdir -p /mnt/pendrive_cinza/cftv_events/reports /var/log"

# 2. Copia os scripts para /usr/local/bin
echo "📦 Copiando scripts para $TARGET_DIR..."
scp scripts/dvr_client.py $ALPINE_HOST:$TARGET_DIR/
scp scripts/dvr_event_listener.py $ALPINE_HOST:$TARGET_DIR/
scp scripts/generate_daily_report.py $ALPINE_HOST:$TARGET_DIR/
scp scripts/prune_cftv_storage.py $ALPINE_HOST:$TARGET_DIR/
scp scripts/audit_nvr_config.py $ALPINE_HOST:$TARGET_DIR/

ssh $ALPINE_HOST "chmod +x $TARGET_DIR/dvr_client.py $TARGET_DIR/dvr_event_listener.py $TARGET_DIR/generate_daily_report.py $TARGET_DIR/prune_cftv_storage.py $TARGET_DIR/audit_nvr_config.py"

# 3. Cria serviço OpenRC no Alpine
echo "⚙️ Configurando serviço OpenRC /etc/init.d/$SERVICE_NAME..."
ssh $ALPINE_HOST "cat << 'EOF' > /etc/init.d/$SERVICE_NAME
#!/sbin/openrc-run

name=\"cftv-events\"
description=\"Daemon de Escuta de Eventos CFTV e Snapshots no Pendrive\"
command=\"/usr/bin/python3\"
command_args=\"/usr/local/bin/dvr_event_listener.py\"
command_background=true
pidfile=\"/run/cftv-events.pid\"
output_log=\"/var/log/cftv-events.log\"
error_log=\"/var/log/cftv-events.err\"

depend() {
    need net
    after firewall
}
EOF
chmod +x /etc/init.d/$SERVICE_NAME
"

# 4. Habilita e reinicia o serviço
echo "🔄 Habilitando e iniciando serviço $SERVICE_NAME..."
ssh $ALPINE_HOST "rc-update add $SERVICE_NAME default 2>/dev/null || true"
ssh $ALPINE_HOST "rc-service $SERVICE_NAME restart"

# 5. Configura cronjob para o Relatório Diário Noturno às 21:00
echo "⏰ Configurando Crontab para o Relatório Diário às 21:00..."
ssh $ALPINE_HOST "
(crontab -l 2>/dev/null | grep -v 'generate_daily_report.py' ; echo '0 21 * * * /usr/bin/python3 /usr/local/bin/generate_daily_report.py >> /var/log/cftv-report.log 2>&1') | crontab -
"

echo "✅ Deploy concluído com sucesso no nó Alpine!"
