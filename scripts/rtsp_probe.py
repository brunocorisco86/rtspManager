#!/usr/bin/env python3
"""
RTSP Probe - Validador e Explorador de Streams RTSP / ONVIF
Testa conectividade, codecs e credenciais no NVR (192.168.1.20) e câmeras IP.
"""

import sys
import json
import subprocess
import socket
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "config" / "cameras.json"

def check_port(ip, port, timeout=1.0):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def probe_rtsp_url(url, timeout=3):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-rtsp_transport", "tcp",
        "-timeout", str(timeout * 1000000),
        "-show_entries", "stream=codec_name,width,height,r_frame_rate",
        "-of", "json",
        url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            streams = data.get("streams", [])
            if streams:
                s = streams[0]
                return True, f"{s.get('codec_name', '?')} {s.get('width', '?')}x{s.get('height', '?')} @ {s.get('r_frame_rate', '?')}fps"
            return True, "Stream detectada"
        elif "401 Unauthorized" in res.stderr:
            return False, "401 Não Autorizado (Requer Senha)"
        else:
            return False, res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "Falha de conexão"
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)

def main():
    if not CONFIG_FILE.exists():
        print(f"Erro: Arquivo {CONFIG_FILE} não encontrado.")
        sys.exit(1)

    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)

    nvr = data.get("nvr", {})
    cameras = data.get("cameras", [])

    print("==================================================")
    print(" 📹 10_RTSP_Manager - Diagnóstico de Conectividade")
    print("==================================================")

    # 1. Checagem do NVR
    nvr_ip = nvr.get("ip")
    print(f"\n[NVR Central] {nvr.get('name')} ({nvr_ip})")
    for svc, port in nvr.get("ports", {}).items():
        status = "OPEN ✅" if check_port(nvr_ip, port) else "CLOSED ❌"
        print(f"  • Porta {port} ({svc}): {status}")

    # 2. Checagem das Câmeras Individuais
    print(f"\n[Câmeras Individuais Detectadas ({len(cameras)})]")
    for cam in cameras:
        cip = cam.get("ip")
        rport = cam.get("rtsp_port", 554)
        rtsp_ok = check_port(cip, rport)
        status = "RTSP ONLINE ✅" if rtsp_ok else "OFFLINE ❌"
        print(f"  • {cam.get('name')} ({cip}): {status}")

    print("\nPara testar um stream específico com senha:")
    print("  ffprobe -rtsp_transport tcp 'rtsp://usuario:senha@192.168.1.20:554/user=admin&password=SUA_SENHA&channel=1&stream=0.sdp'")

if __name__ == "__main__":
    main()
