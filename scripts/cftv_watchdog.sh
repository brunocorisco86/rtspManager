#!/bin/sh
# ==============================================================================
# CCTV Watchdog - Monitor de Integridade dos Canais do NVR (10_RTSP_Manager)
# ==============================================================================
# Monitora a saúde do NVR (192.168.1.20:554) e dos canais ativos (02, 03, 04, 05, 06).
# - Dispara alertas ntfy (bruno-casa-dallas) APENAS na transição de estado (sem fadiga).
# - Se o NVR cair, alerta o NVR e suprime alertas repetidos de cada canal.
# - Testa fluxo real de vídeo via go2rtc (/api/frame.jpeg).
# ==============================================================================

STATE_DIR="/tmp/cftv_states"
mkdir -p "$STATE_DIR"

NVR_IP="192.168.1.20"
NVR_STATE_FILE="${STATE_DIR}/NVR_Principal.state"
PREV_NVR_STATE="UP"
[ -f "$NVR_STATE_FILE" ] && PREV_NVR_STATE=$(cat "$NVR_STATE_FILE")

# 1. Verifica integridade do NVR Principal
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

# Transição do NVR
if [ "$PREV_NVR_STATE" = "UP" ] && [ "$CURRENT_NVR_STATE" = "DOWN" ]; then
    if [ -f "$CFTV_DB_SCRIPT" ]; then
        python3 "$CFTV_DB_SCRIPT" --record --device "NVR_Principal" --device-type "nvr" --event "DISCONNECTED" --new-ip "$NVR_IP" --details "O NVR Principal ($NVR_IP:554) parou de responder às $(date +'%H:%M:%S')." > /dev/null 2>&1
    fi
    if [ "${NOTIFY_NVR_STATUS:-0}" = "1" ]; then
        notifica -t "🚨 CFTV: NVR Principal Offline!" \
                 -p 5 \
                 -g "rotating_light,nvr" \
                 "O NVR Principal ($NVR_IP:554) parou de responder às $(date +'%H:%M:%S'). Possível queda de energia ou cabo de rede desconectado."
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

# 2. Se o NVR estiver UP, testa fluxo real de vídeo de cada um dos 5 canais ativos
if [ "$CURRENT_NVR_STATE" = "UP" ]; then
    for CH in 02 03 04 05 06; do
        CH_STREAM="canal_${CH}"
        CH_STATE_FILE="${STATE_DIR}/${CH_STREAM}.state"
        PREV_CH_STATE="UP"
        [ -f "$CH_STATE_FILE" ] && PREV_CH_STATE=$(cat "$CH_STATE_FILE")

        # Testa captura de quadro via go2rtc local
        if curl -s -f -m 3 "http://127.0.0.1:1984/api/frame.jpeg?src=${CH_STREAM}" -o /dev/null; then
            CURRENT_CH_STATE="UP"
        else
            CURRENT_CH_STATE="DOWN"
        fi
        echo "$CURRENT_CH_STATE" > "$CH_STATE_FILE"

        if [ "${NOTIFY_CFTV_CHANNELS:-0}" = "1" ]; then
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
