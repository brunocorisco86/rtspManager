#!/usr/bin/env python3
"""
==============================================================================
Dynamic Resolver & Self-Healing Orchestrator - 10_RTSP_Manager
==============================================================================
Resolução dinâmica de topologia de CFTV baseada em Hardware ID (MAC Address):
1. Resolve dispositivos por MAC Address (imune a mudanças de DHCP/IP).
2. Permite entrada por MAC, por IP, ou ambos.
3. Detecta transição de IP (IP-change) e alerta via ntfy.
4. Auto-descobre novas câmeras conectadas na rede (porta 554).
5. Gera dinamicamente o config/go2rtc.yaml e recarrega os streams.
6. Mantém o inventário em config/inventory.json.
==============================================================================
"""

import os
import sys
import json
import re
import socket
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "config" / "cameras.json"
INVENTORY_FILE = BASE_DIR / "config" / "inventory.json"
GO2RTC_CONFIG = BASE_DIR / "config" / "go2rtc.yaml"

# Importação resiliente de cftv_db para registro no Postgres (ssh alpine)
sys.path.insert(0, str(Path(__file__).parent))
try:
    from cftv_db import record_event
except ImportError:
    try:
        from scripts.cftv_db import record_event
    except ImportError:
        def record_event(*args, **kwargs):
            return False

# Flags para eliminar fadiga de decisão no ntfy (notificações consolidadas aos domingos)
ALERT_ON_IP_CHANGE = os.getenv("ALERT_ON_IP_CHANGE", "false").lower() in ("true", "1", "yes")
ALERT_ON_CAM_STATUS = os.getenv("ALERT_ON_CAM_STATUS", "false").lower() in ("true", "1", "yes")
ALERT_ON_NVR_STATUS = os.getenv("ALERT_ON_NVR_STATUS", "false").lower() in ("true", "1", "yes")
ALERT_ON_DISCOVER = os.getenv("ALERT_ON_DISCOVER", "false").lower() in ("true", "1", "yes")

def normalize_mac(mac_str):
    if not mac_str:
        return None
    cleaned = re.sub(r'[^0-9a-fA-F]', '', mac_str).lower()
    if len(cleaned) == 12:
        return ":".join(cleaned[i:i+2] for i in range(0, 12, 2))
    return mac_str.lower()

def get_arp_table():
    """
    Lê a tabela ARP do kernel (/proc/net/arp e ip neigh)
    Retorna mapeamentos: {mac: ip} e {ip: mac}
    """
    mac_to_ip = {}
    ip_to_mac = {}

    # 1. Tenta ler direto de /proc/net/arp (Linux nativo / Alpine)
    if os.path.exists("/proc/net/arp"):
        try:
            with open("/proc/net/arp", "r") as f:
                lines = f.readlines()[1:] # ignora header
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 4:
                        ip = parts[0]
                        mac = normalize_mac(parts[3])
                        if mac and mac != "00:00:00:00:00:00":
                            mac_to_ip[mac] = ip
                            ip_to_mac[ip] = mac
        except Exception as e:
            pass

    # 2. Complementa com 'ip neigh' se disponível
    try:
        res = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                # Formato: 192.168.1.20 dev eth0 lladdr 00:12:43:24:4e:c6 REACHABLE
                m = re.search(r'(\d+\.\d+\.\d+\.\d+).*?lladdr\s+([0-9a-fA-F:]{17})', line)
                if m:
                    ip = m.group(1)
                    mac = normalize_mac(m.group(2))
                    mac_to_ip[mac] = ip
                    ip_to_mac[ip] = mac
    except Exception:
        pass

    return mac_to_ip, ip_to_mac

def check_port(ip, port=554, timeout=0.8):
    """Testa se uma porta TCP está respondendo"""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def ping_host(ip):
    """Aquece o cache ARP com um ping ICMP rápido de 1 pacote"""
    try:
        subprocess.run(["ping", "-c", "1", "-W", "1", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.2)
    except Exception:
        pass

def send_notification(title, message, priority="3", tags="camera"):
    """Dispara notificação via comando 'notifica' ou HTTP direto ntfy"""
    try:
        subprocess.run(
            ["notifica", "-t", title, "-p", str(priority), "-g", tags, message],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3
        )
    except Exception:
        try:
            topic = os.getenv("NTFY_TOPIC", "bruno-casa-dallas")
            req = urllib.request.Request(
                f"https://ntfy.sh/{topic}",
                data=message.encode('utf-8'),
                headers={"Title": title, "Priority": str(priority), "Tags": tags}
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass

def generate_go2rtc_yaml(nvr_info, resolved_cameras):
    """Gera o arquivo go2rtc.yaml com base nos IPs e canais resolvidos dinamicamente"""
    nvr_ip = nvr_info.get("resolved_ip") or nvr_info.get("ip")
    nvr_user = nvr_info.get("user", "admin")
    nvr_pass = nvr_info.get("password", "")

    lines = [
        "# ==============================================================================",
        "# go2rtc Configuration (Gerado Automaticamente pelo Dynamic Resolver)",
        f"# Atualizado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "# Modo Passthrough / Zero Transcoding (Otimizado para Raspberry Pi 3)",
        "# ==============================================================================",
        "",
        "api:",
        "  listen: \":1984\"",
        "",
        "rtsp:",
        "  listen: \":8554\"",
        "",
        "webrtc:",
        "  listen: \":8555\"",
        "",
        "streams:"
    ]

    # Streams do NVR (Canais 1 a 6)
    if nvr_ip:
        lines.append("  # --- Canais Centralizados via NVR ---")
        for ch in range(1, 7):
            url = f"rtsp://{nvr_user}:{nvr_pass}@{nvr_ip}:554/user={nvr_user}&password={nvr_pass}&channel={ch}&stream=0.sdp#backchannel=0"
            lines.append(f"  nvr_canal{ch}:")
            lines.append(f"    - {url}")

    # Streams Diretos das Câmeras Resolvidas
    lines.append("")
    lines.append("  # --- Streams Diretos das Câmeras (IP Resolvido por MAC) ---")
    for cam in resolved_cameras:
        if cam.get("status") == "ONLINE" and cam.get("resolved_ip"):
            c_name = re.sub(r'[^a-zA-Z0-9_]', '_', cam.get("name", "cam")).lower()
            c_ip = cam.get("resolved_ip")
            c_user = cam.get("user", "admin")
            c_pass = cam.get("password", "")
            url = f"rtsp://{c_user}:{c_pass}@{c_ip}:554/user={c_user}&password={c_pass}&channel=1&stream=0.sdp"
            lines.append(f"  {c_name}:")
            lines.append(f"    - {url}")

    lines.append("")
    lines.append("log:")
    lines.append("  level: info")
    lines.append("")

    return "\n".join(lines)

def reload_go2rtc():
    """Solicita reload dos streams via API REST do go2rtc (se estiver em execução)"""
    try:
        req = urllib.request.Request("http://127.0.0.1:1984/api/restart", data=b"", method="POST")
        urllib.request.urlopen(req, timeout=2)
        print("  🔄 go2rtc recarregado com sucesso via API local.")
    except Exception:
        pass

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Iniciando Reconciliação Dinâmica de CFTV...")

    if not CONFIG_FILE.exists():
        print(f"Erro: {CONFIG_FILE} não encontrado.")
        sys.exit(1)

    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)

    # Carrega inventário anterior para comparar mudanças
    inventory = {}
    if INVENTORY_FILE.exists():
        try:
            with open(INVENTORY_FILE, "r") as f:
                inventory = json.load(f)
        except Exception:
            inventory = {}

    nvr = config.get("nvr", {})
    cameras = config.get("cameras", [])

    # Aquece cache ARP de todos os IPs conhecidos
    known_ips = []
    if nvr.get("ip"):
        known_ips.append(nvr.get("ip"))
    for c in cameras:
        if c.get("ip"):
            known_ips.append(c.get("ip"))
    
    for ip in known_ips:
        ping_host(ip)

    mac_to_ip, ip_to_mac = get_arp_table()

    # 1. Resolve NVR
    nvr_mac = normalize_mac(nvr.get("mac"))
    nvr_ip = nvr.get("ip")
    resolved_nvr_ip = None

    if nvr_mac and nvr_mac in mac_to_ip:
        resolved_nvr_ip = mac_to_ip[nvr_mac]
    elif nvr_ip and check_port(nvr_ip, 554):
        resolved_nvr_ip = nvr_ip
        if nvr_ip in ip_to_mac and not nvr_mac:
            nvr["mac"] = ip_to_mac[nvr_ip]

    nvr["resolved_ip"] = resolved_nvr_ip
    nvr_status = "ONLINE" if (resolved_nvr_ip and check_port(resolved_nvr_ip, 554)) else "OFFLINE"
    nvr["status"] = nvr_status

    prev_nvr = inventory.get("nvr", {})
    prev_nvr_ip = prev_nvr.get("resolved_ip")
    prev_nvr_status = prev_nvr.get("status")

    # Detecta e registra mudança de IP do NVR
    if prev_nvr_ip and resolved_nvr_ip and prev_nvr_ip != resolved_nvr_ip:
        print(f"  🔄 NVR mudou de IP: {prev_nvr_ip} -> {resolved_nvr_ip}. Registrando no Postgres...")
        record_event(
            device_name=nvr.get("name", "NVR_Principal"),
            device_type="nvr",
            event_type="IP_CHANGED",
            old_ip=prev_nvr_ip,
            new_ip=resolved_nvr_ip,
            mac_address=nvr_mac,
            details=f"O NVR foi realocado de {prev_nvr_ip} para {resolved_nvr_ip}"
        )
        if ALERT_ON_IP_CHANGE:
            send_notification("🔄 NVR Mudou de IP", f"O NVR foi realocado de {prev_nvr_ip} para {resolved_nvr_ip}", priority="4", tags="warning,video_camera")

    # Detecta transição de status do NVR
    if prev_nvr_status == "ONLINE" and nvr_status == "OFFLINE":
        print("  🚨 NVR Principal Offline! Registrando no Postgres...")
        record_event(
            device_name=nvr.get("name", "NVR_Principal"),
            device_type="nvr",
            event_type="DISCONNECTED",
            old_ip=prev_nvr_ip,
            new_ip=resolved_nvr_ip,
            mac_address=nvr_mac,
            details="NVR Principal parou de responder na porta 554"
        )
        if ALERT_ON_NVR_STATUS:
            send_notification("🚨 CFTV: NVR Principal Offline!", f"O NVR Principal ({resolved_nvr_ip or nvr_ip}:554) parou de responder.", priority="5", tags="rotating_light,nvr")
    elif prev_nvr_status == "OFFLINE" and nvr_status == "ONLINE":
        print("  ✅ NVR Principal Restabelecido! Registrando no Postgres...")
        record_event(
            device_name=nvr.get("name", "NVR_Principal"),
            device_type="nvr",
            event_type="RECONNECTED",
            old_ip=prev_nvr_ip,
            new_ip=resolved_nvr_ip,
            mac_address=nvr_mac,
            details="NVR Principal restabelecido e operando normalmente"
        )
        if ALERT_ON_NVR_STATUS:
            send_notification("✅ CFTV: NVR Principal Restabelecido", f"O NVR Principal ({resolved_nvr_ip}) voltou a operar normalmente.", priority="3", tags="white_check_mark,nvr")

    print(f"  • NVR: {nvr.get('name')} | MAC: {nvr_mac} | IP Resolvido: {resolved_nvr_ip} | Status: {nvr_status}")

    # 2. Resolve Câmeras
    resolved_cameras = []
    for cam in cameras:
        c_mac = normalize_mac(cam.get("mac"))
        c_ip = cam.get("ip")
        c_name = cam.get("name")
        resolved_ip = None

        if c_mac and c_mac in mac_to_ip:
            resolved_ip = mac_to_ip[c_mac]
        elif c_ip and check_port(c_ip, 554):
            resolved_ip = c_ip
            if c_ip in ip_to_mac and not c_mac:
                cam["mac"] = ip_to_mac[c_ip]

        status = "ONLINE" if (resolved_ip and check_port(resolved_ip, 554)) else "OFFLINE"

        prev_cam = inventory.get("cameras", {}).get(c_name, {})
        prev_cam_ip = prev_cam.get("resolved_ip")
        prev_cam_status = prev_cam.get("status")

        # Detecta e registra mudança de IP da Câmera
        if prev_cam_ip and resolved_ip and prev_cam_ip != resolved_ip:
            print(f"  🔄 Câmera {c_name} mudou de IP: {prev_cam_ip} -> {resolved_ip}. Registrando no Postgres...")
            record_event(
                device_name=c_name,
                device_type="camera",
                event_type="IP_CHANGED",
                old_ip=prev_cam_ip,
                new_ip=resolved_ip,
                mac_address=c_mac,
                details=f"A {c_name} mudou de IP: {prev_cam_ip} -> {resolved_ip}"
            )
            if ALERT_ON_IP_CHANGE:
                send_notification("🔄 Câmera Mudou de IP", f"A {c_name} mudou de IP: {prev_cam_ip} -> {resolved_ip}", priority="3", tags="information_source,camera")

        # Detecta e registra transição de status (desconexão/reconexão)
        if prev_cam_status == "ONLINE" and status == "OFFLINE":
            print(f"  ⚠️ Câmera {c_name} desconectou (OFFLINE). Registrando no Postgres...")
            record_event(
                device_name=c_name,
                device_type="camera",
                event_type="DISCONNECTED",
                old_ip=prev_cam_ip or resolved_ip,
                new_ip=resolved_ip,
                mac_address=c_mac,
                details=f"A {c_name} desconectou (porta 554 fechada ou sem resposta)"
            )
            if ALERT_ON_CAM_STATUS:
                send_notification("⚠️ CFTV: Câmera Sem Vídeo", f"A {c_name} perdeu sinal.", priority="4", tags="warning,camera")
        elif prev_cam_status == "OFFLINE" and status == "ONLINE":
            print(f"  ✅ Câmera {c_name} restabelecida (ONLINE). Registrando no Postgres...")
            record_event(
                device_name=c_name,
                device_type="camera",
                event_type="RECONNECTED",
                old_ip=prev_cam_ip,
                new_ip=resolved_ip,
                mac_address=c_mac,
                details=f"A {c_name} restabeleceu conexão em {resolved_ip}"
            )
            if ALERT_ON_CAM_STATUS:
                send_notification("✅ CFTV: Câmera Restabelecida", f"A {c_name} voltou a operar em {resolved_ip}.", priority="3", tags="white_check_mark,camera")

        cam_record = {
            "name": c_name,
            "mac": c_mac,
            "configured_ip": c_ip,
            "resolved_ip": resolved_ip,
            "nvr_channel": cam.get("nvr_channel"),
            "status": status,
            "user": cam.get("user", "admin"),
            "password": cam.get("password", ""),
            "last_seen": datetime.now().isoformat() if status == "ONLINE" else inventory.get("cameras", {}).get(c_name, {}).get("last_seen")
        }
        resolved_cameras.append(cam_record)
        print(f"  • Câmera: {c_name} | MAC: {c_mac} | IP: {resolved_ip} | Status: {status}")

    # 3. Auto-Descoberta de Novas Câmeras
    settings = config.get("settings", {})
    if settings.get("auto_discover_new_cameras"):
        subnet_base = "192.168.1."
        registered_ips = {c["resolved_ip"] for c in resolved_cameras if c["resolved_ip"]}
        if resolved_nvr_ip:
            registered_ips.add(resolved_nvr_ip)

        for mac, ip in mac_to_ip.items():
            if ip.startswith(subnet_base) and ip not in registered_ips:
                if check_port(ip, 554):
                    print(f"  ✨ Nova Câmera Detectada: IP {ip} | MAC {mac}. Registrando no Postgres...")
                    new_cam = {
                        "name": f"Discovered_Cam_{ip.split('.')[-1]}",
                        "mac": mac,
                        "configured_ip": ip,
                        "resolved_ip": ip,
                        "nvr_channel": None,
                        "status": "ONLINE",
                        "user": "admin",
                        "password": "",
                        "last_seen": datetime.now().isoformat()
                    }
                    resolved_cameras.append(new_cam)
                    record_event(
                        device_name=new_cam["name"],
                        device_type="camera",
                        event_type="DISCOVERED",
                        old_ip=None,
                        new_ip=ip,
                        mac_address=mac,
                        details=f"Nova câmera IP detectada na rede: {ip} (MAC: {mac})"
                    )
                    if ALERT_ON_DISCOVER:
                        send_notification("✨ Nova Câmera Detectada", f"Nova câmera IP detectada na rede: {ip} (MAC: {mac})", priority="3", tags="sparkles,camera")

    # 4. Salva Inventário em config/inventory.json
    new_inventory = {
        "updated_at": datetime.now().isoformat(),
        "nvr": nvr,
        "cameras": {c["name"]: c for c in resolved_cameras}
    }
    with open(INVENTORY_FILE, "w") as f:
        json.dump(new_inventory, f, indent=2)

    # 5. Gera e Atualiza go2rtc.yaml
    new_yaml = generate_go2rtc_yaml(nvr, resolved_cameras)
    yaml_changed = True
    if GO2RTC_CONFIG.exists():
        old_yaml = GO2RTC_CONFIG.read_text()
        # Ignora linha de data para comparação de alteração real de streams
        def strip_date(txt):
            return "\n".join(l for l in txt.splitlines() if not l.startswith("# Atualizado em:"))
        if strip_date(old_yaml) == strip_date(new_yaml):
            yaml_changed = False

    if yaml_changed:
        with open(GO2RTC_CONFIG, "w") as f:
            f.write(new_yaml)
        print("  📝 config/go2rtc.yaml atualizado com os streams resolvidos.")
        reload_go2rtc()
    else:
        print("  ⚡ Nenhuma alteração de streams necessária no go2rtc.yaml.")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Reconciliação concluída com sucesso.\n")

if __name__ == "__main__":
    main()
