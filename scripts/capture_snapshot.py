#!/usr/bin/env python3
"""
Capture Snapshot - Extrai um frame JPEG de uma câmera via RTSP ou go2rtc API
e opcionalmente dispara para o ntfy (bruno-casa-dallas).
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "bruno-casa-dallas")

def capture_via_ffmpeg(rtsp_url, output_path, timeout=5):
    cmd = [
        "ffmpeg",
        "-y",
        "-rtsp_transport", "tcp",
        "-timeout", str(timeout * 1000000),
        "-i", rtsp_url,
        "-vframes", "1",
        "-q:v", "2",
        output_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 3)
        return res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"Erro no ffmpeg: {e}")
        return False

def capture_via_go2rtc(go2rtc_host, stream_name, output_path):
    import urllib.request
    url = f"http://{go2rtc_host}:1984/api/frame.jpeg?src={stream_name}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.read())
                return True
    except Exception as e:
        print(f"Erro ao capturar via go2rtc: {e}")
    return False

def send_to_ntfy_curl(image_path, title="Captura CFTV", message="Frame capturado com sucesso"):
    filename = os.path.basename(image_path)
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    cmd = [
        "curl", "-s",
        "-T", image_path,
        "-H", f"Title: {title}",
        "-H", f"Message: {message}",
        "-H", f"Filename: {filename}",
        url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return res.returncode == 0 and "attachment" in res.stdout
    except Exception as e:
        print(f"Erro ao enviar ntfy via curl: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Captura de frames de CFTV e envio via ntfy")
    parser.add_argument("--url", help="URL RTSP completa da câmera")
    parser.add_argument("--go2rtc", default="192.168.1.99", help="IP do servidor go2rtc (padrão: 192.168.1.99)")
    parser.add_argument("--src", help="Nome do stream no go2rtc (ex: nvr_canal1, cam_04)")
    parser.add_argument("--out", default="/tmp/snapshot.jpg", help="Caminho do arquivo local de saída")
    parser.add_argument("--ntfy", action="store_true", help="Envia o snapshot capturado para o canal ntfy")
    parser.add_argument("--title", default="Camera Alerta", help="Título do alerta ntfy")
    parser.add_argument("--msg", default="Snapshot ao vivo da camera", help="Mensagem do alerta")
    args = parser.parse_args()

    success = False
    if args.src:
        print(f"Capturando frame via go2rtc ({args.src})...")
        success = capture_via_go2rtc(args.go2rtc, args.src, args.out)
    elif args.url:
        print(f"Capturando frame via RTSP direto...")
        success = capture_via_ffmpeg(args.url, args.out)
    else:
        print("Informe --src <stream_go2rtc> ou --url <rtsp_url>")
        sys.exit(1)

    if success:
        print(f"✅ Snapshot salvo em {args.out} ({os.path.getsize(args.out)} bytes)")
        if args.ntfy:
            print("Enviando foto para o celular via ntfy...")
            if send_to_ntfy_curl(args.out, title=args.title, message=args.msg):
                print("📱 Foto entregue com sucesso no app ntfy!")
            else:
                print("❌ Falha ao enviar para o ntfy.")
    else:
        print("❌ Falha na captura do frame.")
        sys.exit(1)

if __name__ == "__main__":
    main()
