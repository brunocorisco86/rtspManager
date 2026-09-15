#!/bin/sh
# ==============================================================================
# CCTV Watchdog - Monitor de Integridade do Parque de Câmeras e NVR
# ==============================================================================
# Verifica a porta RTSP 554 de cada uma das 6 câmeras e do NVR.
# Envia alerta push imediato via notifica se alguma câmera cair ou voltar.
# ==============================================================================

STATE_DIR="/tmp/cftv_states"
mkdir -p "$STATE_DIR"

check_camera() {
    NAME="$1"
    IP="$2"
    PORT="${3:-554}"

    STATE_FILE="${STATE_DIR}/${NAME}.state"
    PREV_STATE="UP"
    [ -f "$STATE_FILE" ] && PREV_STATE=$(cat "$STATE_FILE")

    if nc -z -w 2 "$IP" "$PORT" > /dev/null 2>&1; then
        CURRENT_STATE="UP"
    else
        CURRENT_STATE="DOWN"
    fi

    echo "$CURRENT_STATE" > "$STATE_FILE"

    if [ "$PREV_STATE" = "UP" ] && [ "$CURRENT_STATE" = "DOWN" ]; then
        notifica -t "🚨 CFTV: $NAME Caiu!" \
                 -p 4 \
                 -g "rotating_light,camera" \
                 "A câmera $NAME ($IP:$PORT) parou de responder ao RTSP às $(date +'%H:%M:%S')."
    elif [ "$PREV_STATE" = "DOWN" ] && [ "$CURRENT_STATE" = "UP" ]; then
        notifica -t "✅ CFTV: $NAME Recuperada" \
                 -p 3 \
                 -g "white_check_mark,camera" \
                 "A câmera $NAME ($IP) voltou a operar normalmente às $(date +'%H:%M:%S')."
    fi
}

# NVR Central
check_camera "NVR_Principal" "192.168.1.20" 554

# 6 Câmeras Individuais
check_camera "Camera_04" "192.168.1.4" 554
check_camera "Camera_05" "192.168.1.5" 554
check_camera "Camera_06" "192.168.1.6" 554
check_camera "Camera_10" "192.168.1.10" 554
check_camera "Camera_11" "192.168.1.11" 554
check_camera "Camera_31" "192.168.1.31" 554
