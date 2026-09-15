#!/bin/sh
# ==============================================================================
# Script de Instalação Nativa do go2rtc no Alpine Linux (Nó Peixe)
# ==============================================================================
set -e

echo "==> Baixando binário oficial do go2rtc para aarch64 (ARM64)..."
LATEST_URL="https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm64"
wget -O /usr/local/bin/go2rtc "$LATEST_URL"
chmod +x /usr/local/bin/go2rtc

echo "==> Criando diretório de configuração em /etc/go2rtc..."
mkdir -p /etc/go2rtc

echo "==> Criando serviço OpenRC /etc/init.d/go2rtc..."
cat << 'INIT' > /etc/init.d/go2rtc
#!/sbin/openrc-run
description="go2rtc streaming service"
supervisor=supervise-daemon
name="go2rtc"
command="/usr/local/bin/go2rtc"
command_args="-c /etc/go2rtc/go2rtc.yaml"
command_background=true
pidfile="/run/go2rtc.pid"

depend() {
    need net
    after firewall
}
INIT

chmod +x /etc/init.d/go2rtc

echo "==> Instalação concluída com sucesso!"
echo "Para iniciar:"
echo "  rc-service go2rtc start"
echo "  rc-update add go2rtc default"
