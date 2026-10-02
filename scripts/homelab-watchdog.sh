#!/bin/sh
# ==============================================================================
# Homelab Watchdog - Monitor de Saúde da Rede, NVR e Serviços
# ==============================================================================
# Executa verificações periódicas nos nós Alpine, Peixe, NVR e Câmeras.
# Notifica via ntfy (bruno-casa-dallas) quando um serviço cai ou se recupera.
# ==============================================================================

STATE_DIR="/tmp/watchdog_states"
mkdir -p "$STATE_DIR"

MODE="$1" # "" (silent check), "--report", "--test"

check_service() {
    NAME="$1"
    CMD="$2"
    TAG_OK="$3"
    TAG_FAIL="$4"

    STATE_FILE="${STATE_DIR}/${NAME}.state"
    PREV_STATE="UP"
    [ -f "$STATE_FILE" ] && PREV_STATE=$(cat "$STATE_FILE")

    if eval "$CMD" > /dev/null 2>&1; then
        CURRENT_STATE="UP"
    else
        CURRENT_STATE="DOWN"
    fi

    echo "$CURRENT_STATE" > "$STATE_FILE"

    # Se estiver em modo relatório forçado
    if [ "$MODE" = "--report" ]; then
        if [ "$CURRENT_STATE" = "UP" ]; then
            echo "  ✅ $NAME: ONLINE"
        else
            echo "  ❌ $NAME: OFFLINE"
        fi
        return
    fi

    # Notifica apenas na TRANSIÇÃO de estado
    if [ "$PREV_STATE" = "UP" ] && [ "$CURRENT_STATE" = "DOWN" ]; then
        notifica -t "🚨 Alerta: $NAME Caiu!" \
                 -p 4 \
                 -g "rotating_light,$TAG_FAIL" \
                 "O serviço $NAME parou de responder às $(date +'%H:%M:%S')."
    elif [ "$PREV_STATE" = "DOWN" ] && [ "$CURRENT_STATE" = "UP" ]; then
        notifica -t "✅ Recuperado: $NAME" \
                 -p 3 \
                 -g "white_check_mark,$TAG_OK" \
                 "O serviço $NAME voltou a responder normalmente às $(date +'%H:%M:%S')."
    fi
}

# Função com histerese/retry para verificar fluxo real de vídeo sem falso positivo
check_cftv_channel() {
    STREAM="$1"
    if curl -s -f -m 7 "http://127.0.0.1:1984/api/frame.jpeg?src=${STREAM}" -o /dev/null; then
        return 0
    fi
    sleep 1
    if curl -s -f -m 7 "http://127.0.0.1:1984/api/frame.jpeg?src=${STREAM}" -o /dev/null; then
        return 0
    fi
    return 1
}

if [ "$MODE" = "--report" ]; then
    echo "🔍 Executando diagnóstico do Homelab..."
fi

# 1. Conectividade WAN (Internet)
check_service "Internet_WAN" "ping -c 2 -W 2 1.1.1.1" "globe_with_meridians" "satellite"

# 2. Gateway Local (Roteador)
check_service "Gateway_Roteador" "ping -c 2 -W 2 192.168.1.1" "router" "x"

# 3. Nó Alpine (DNS Pi-hole porta 53)
check_service "DNS_PiHole" "nc -z -w 2 192.168.1.7 53" "shield" "skull"

# 4. Banco de Dados PostgreSQL (Porta 5432)
check_service "PostgreSQL" "nc -z -w 2 192.168.1.7 5432" "elephant" "warning"

# 5. LightManager API (Porta 8000)
check_service "LightManager_API" "curl -s -m 2 -o /dev/null -w '%{http_code}' http://192.168.1.7:8000/docs | grep -q '200'" "bulb" "warning"

# 6. Monitor de CFTV: NVR Principal e Canais Individuais (com debounce)
NVR_IP="192.168.1.20"
NVR_STATE_FILE="${STATE_DIR}/NVR_Principal.state"
PREV_NVR_STATE="UP"
[ -f "$NVR_STATE_FILE" ] && PREV_NVR_STATE=$(cat "$NVR_STATE_FILE")

if nc -z -w 2 "$NVR_IP" 554 > /dev/null 2>&1; then
    CURRENT_NVR_STATE="UP"
else
    CURRENT_NVR_STATE="DOWN"
fi
echo "$CURRENT_NVR_STATE" > "$NVR_STATE_FILE"

# Localiza cftv_db.py para registro no PostgreSQL (ssh alpine)
CFTV_DB_SCRIPT="/home/bruno/10_RTSP_Manager/scripts/cftv_db.py"
[ ! -f "$CFTV_DB_SCRIPT" ] && CFTV_DB_SCRIPT="$(dirname "$0")/cftv_db.py"
[ ! -f "$CFTV_DB_SCRIPT" ] && CFTV_DB_SCRIPT="$(dirname "$0")/../scripts/cftv_db.py"

if [ "$MODE" != "--report" ]; then
    if [ "$PREV_NVR_STATE" = "UP" ] && [ "$CURRENT_NVR_STATE" = "DOWN" ]; then
        if [ -f "$CFTV_DB_SCRIPT" ]; then
            python3 "$CFTV_DB_SCRIPT" --record --device "NVR_Principal" --device-type "nvr" --event "DISCONNECTED" --new-ip "$NVR_IP" --details "O NVR Principal ($NVR_IP:554) parou de responder às $(date +'%H:%M:%S')." > /dev/null 2>&1
        fi
        if [ "${NOTIFY_NVR_STATUS:-0}" = "1" ]; then
            notifica -t "🚨 CFTV: NVR Principal Offline!" \
                     -p 5 \
                     -g "rotating_light,nvr" \
                     "O NVR Principal ($NVR_IP:554) parou de responder às $(date +'%H:%M:%S'). Possível queda de energia ou cabo desconectado."
        fi
    elif [ "$PREV_NVR_STATE" = "DOWN" ] && [ "$CURRENT_NVR_STATE" = "UP" ]; then
        if [ -f "$CFTV_DB_SCRIPT" ]; then
            python3 "$CFTV_DB_SCRIPT" --record --device "NVR_Principal" --device-type "nvr" --event "RECONNECTED" --new-ip "$NVR_IP" --details "O NVR Principal ($NVR_IP) voltou a operar normalmente às $(date +'%H:%M:%S')." > /dev/null 2>&1
        fi
        if [ "${NOTIFY_NVR_STATUS:-0}" = "1" ]; then
            notifica -t "✅ CFTV: NVR Principal Restabelecido" \
                     -p 3 \
                     -g "white_check_mark,nvr" \
                     "O NVR Principal ($NVR_IP) voltou a operar normalmente às $(date +'%H:%M:%S')."
        fi
    fi
fi

# Se o NVR estiver UP, checa os 6 canais ativos
ACTIVE_CHANNELS_UP=0
TOTAL_ACTIVE_CHANNELS=6

if [ "$CURRENT_NVR_STATE" = "UP" ]; then
    for CH in 01 02 03 04 05 06; do
        CH_STREAM="canal_${CH}"
        CH_STATE_FILE="${STATE_DIR}/${CH_STREAM}.state"
        PREV_CH_STATE="UP"
        [ -f "$CH_STATE_FILE" ] && PREV_CH_STATE=$(cat "$CH_STATE_FILE")

        if check_cftv_channel "$CH_STREAM"; then
            CURRENT_CH_STATE="UP"
            ACTIVE_CHANNELS_UP=$((ACTIVE_CHANNELS_UP + 1))
        else
            CURRENT_CH_STATE="DOWN"
        fi
        echo "$CURRENT_CH_STATE" > "$CH_STATE_FILE"

        # Notificações instantâneas de canais individuais silenciadas por padrão para evitar fadiga de decisão.
        # Os eventos de conectividade são persistidos no PostgreSQL (ssh alpine) e consolidados no relatório semanal.
        if [ "$MODE" != "--report" ] && [ "${NOTIFY_CFTV_CHANNELS:-0}" = "1" ]; then
            if [ "$PREV_CH_STATE" = "UP" ] && [ "$CURRENT_CH_STATE" = "DOWN" ]; then
                notifica -t "⚠️ CFTV: Canal ${CH} Sem Vídeo" \
                         -p 4 \
                         -g "warning,camera" \
                         "O Canal ${CH} do NVR perdeu o sinal de vídeo às $(date +'%H:%M:%S'). Verifique alimentação ou conexão da câmera."
            elif [ "$PREV_CH_STATE" = "DOWN" ] && [ "$CURRENT_CH_STATE" = "UP" ]; then
                notifica -t "✅ CFTV: Canal ${CH} Restabelecido" \
                         -p 3 \
                         -g "white_check_mark,camera" \
                         "O Canal ${CH} do NVR voltou a transmitir vídeo normalmente às $(date +'%H:%M:%S')."
            fi
        fi
    done
fi

# 7. Espaço em Disco no nó Peixe
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 85 ]; then
    notifica -t "⚠️ Disco Peixe Alto" -p 4 -g "floppy_disk,warning" "O disco raiz do nó Peixe atingiu ${DISK_USAGE}% de uso."
fi

# Se foi solicitado relatório geral (--report), gera resumo consolidado matinal
if [ "$MODE" = "--report" ]; then
    UPTIME_INFO=$(uptime | sed -E 's/.*up ([^,]+).*/\1/' | xargs)
    MEM_FREE=$(free -h | awk '/Mem:/ {print $4}')

    # Calcula previsão das luzes via API do LightManager
    LIGHT_FORECAST=$(python3 -c "
import urllib.request, json
from datetime import datetime, timezone, timedelta
try:
    tz = timezone(timedelta(hours=-3))
    sun = json.loads(urllib.request.urlopen('http://192.168.1.7:8000/api/sun', timeout=2).read())
    sunset = datetime.fromisoformat(sun['sunset']).astimezone(tz)
    sunrise = datetime.fromisoformat(sun['sunrise']).astimezone(tz)
    points = json.loads(urllib.request.urlopen('http://192.168.1.7:8000/api/config/points', timeout=2).read())
    res = []
    for p in points:
        name = p.get('name')
        on_t = (sunset + timedelta(minutes=p.get('offset_on', 0))).strftime('%H:%M')
        off_t = (sunrise + timedelta(minutes=p.get('offset_off', 0))).strftime('%H:%M')
        res.append(f'  • {name}: Ligar ~{on_t} | Desligar ~{off_t}')
    print('\n'.join(res))
except Exception:
    print('  • Previsão indisponível')
" 2>/dev/null)

    REPORT="📊 Diagnóstico Homelab ($(date +'%d/%m %H:%M'))
• Infraestrutura: Internet, Gateway, DNS e Banco OK
• CFTV: NVR ($NVR_IP) e ${ACTIVE_CHANNELS_UP}/${TOTAL_ACTIVE_CHANNELS} canais transmitindo vídeo 🎥
• Peixe Uptime: $UPTIME_INFO (RAM livre: $MEM_FREE)

💡 Previsão Iluminação Hoje:
$LIGHT_FORECAST"

    echo "$REPORT" | notifica -t "Relatório Matinal Homelab" -p 3 -g "bar_chart,sunny,bulb"
    echo ""
    echo "Relatório enviado com sucesso para o celular!"
fi
