#!/usr/bin/env python3
"""
==============================================================================
Weekly CFTV & Network Connectivity Report - 10_RTSP_Manager
==============================================================================
Gera o relatório consolidado semanal de conectividade de CFTV aos domingos.
- Consulta o histórico no banco PostgreSQL em ssh alpine (cftv_network_events).
- Consolida trocas de IP, desconexões/reconexões e câmeras mais instáveis.
- Exibe o status atual de cada dispositivo da malha de segurança.
- Dispara notificação estruturada via ntfy (bruno-casa-dallas), eliminando a
  fadiga de decisão durante a semana.
==============================================================================
"""

import os
import sys
import json
import argparse
import urllib.request
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
INVENTORY_FILE = BASE_DIR / "config" / "inventory.json"
CAMERAS_FILE = BASE_DIR / "config" / "cameras.json"

sys.path.insert(0, str(BASE_DIR / "scripts"))
try:
    from cftv_db import get_weekly_stats, get_events
except ImportError:
    from scripts.cftv_db import get_weekly_stats, get_events

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "bruno-casa-dallas")


def send_report_ntfy(title: str, message: str, priority: str = "3", tags: str = "calendar,camera,bar_chart") -> bool:
    """Envia o relatório semanal via comando 'notifica' ou HTTP direto ntfy"""
    # 1. Tenta via binário 'notifica' do homelab
    try:
        res = subprocess.run(
            ["notifica", "-t", title, "-p", str(priority), "-g", tags, message],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
        )
        if res.returncode == 0:
            print("📱 Relatório entregue via comando 'notifica'.")
            return True
    except Exception:
        pass

    # 2. Fallback via HTTP direto
    try:
        url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"
        req = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": str(priority),
                "Tags": tags,
                "Markdown": "yes"
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                print(f"📱 Relatório entregue com sucesso via HTTP ({url}).")
                return True
    except Exception as e:
        print(f"❌ Falha ao enviar relatório via ntfy: {e}", file=sys.stderr)

    return False


def build_weekly_report(days: int = 7) -> str:
    """Constrói a mensagem consolidada do relatório semanal."""
    now = datetime.now()
    start_date = now - timedelta(days=days)
    period_str = f"{start_date.strftime('%d/%m')} a {now.strftime('%d/%m/%Y')}"

    stats = get_weekly_stats(days=days)
    
    # Carrega inventário atual
    inventory = {}
    if INVENTORY_FILE.exists():
        try:
            with open(INVENTORY_FILE, "r") as f:
                inventory = json.load(f)
        except Exception:
            inventory = {}

    lines = [
        f"📊 **Relatório Semanal CFTV & Rede**",
        f"🗓️ Período: {period_str}",
        ""
    ]

    # 1. Resumo Quantitativo
    if stats.get("available"):
        counts = stats.get("counts_by_type", {})
        ip_changes = counts.get("IP_CHANGED", 0)
        disconnects = counts.get("DISCONNECTED", 0)
        reconnects = counts.get("RECONNECTED", 0)
        discovered = counts.get("DISCOVERED", 0)

        lines.append("📈 **Resumo de Conectividade:**")
        lines.append(f"• 🔄 Trocas de IP registradas: **{ip_changes}**")
        lines.append(f"• ⚠️ Quedas/Desconexões: **{disconnects}**")
        lines.append(f"• ✅ Reconexões automáticas: **{reconnects}**")
        if discovered > 0:
            lines.append(f"• ✨ Novas câmeras detectadas: **{discovered}**")
        lines.append("")

        # 2. Ranking de Instabilidade
        ranking = stats.get("ranking", [])
        instable_devices = [r for r in ranking if (r.get("disconnects", 0) > 0 or r.get("ip_changes", 0) > 0)]
        if instable_devices:
            lines.append("🔍 **Dispositivos com Oscilações:**")
            for r in instable_devices[:5]:
                name = r.get("device_name")
                dis = r.get("disconnects", 0)
                ipc = r.get("ip_changes", 0)
                details = []
                if dis > 0:
                    details.append(f"{dis} quedas")
                if ipc > 0:
                    details.append(f"{ipc} trocas de IP")
                lines.append(f"• **{name}**: {', '.join(details)}")
            lines.append("")

            # Destaque para NVR se tiver oscilado
            nvr_instability = next((r for r in ranking if "nvr" in r.get("device_name", "").lower()), None)
            if nvr_instability and (nvr_instability.get("disconnects", 0) > 0 or nvr_instability.get("ip_changes", 0) > 0):
                lines.append(f"⚠️ *Nota NVR:* O NVR Principal registrou {nvr_instability.get('disconnects', 0)} quedas no período (todas consolidadas aqui).\n")
        else:
            lines.append("✨ **Estabilidade:** Nenhuma oscilação crítica na semana!\n")

    else:
        err = stats.get("error", "Desconhecido")
        lines.append(f"⚠️ *Nota: Banco Postgres em alpine indisponível ({err}).*\n")

    # 3. Status Atual da Infraestrutura (Snapshot em Tempo Real)
    lines.append("📹 **Status Atual da Infraestrutura:**")
    nvr = inventory.get("nvr", {})
    nvr_status = nvr.get("status", "UNKNOWN")
    nvr_ip = nvr.get("resolved_ip") or nvr.get("ip", "N/A")
    nvr_icon = "🟢" if nvr_status == "ONLINE" else "🔴"
    lines.append(f"• {nvr_icon} **{nvr.get('name', 'NVR_Principal')}**: {nvr_status} ({nvr_ip})")

    cameras = inventory.get("cameras", {})
    online_count = 0
    total_count = len(cameras)

    for cam_name, cam_info in sorted(cameras.items()):
        status = cam_info.get("status", "UNKNOWN")
        ip = cam_info.get("resolved_ip") or cam_info.get("configured_ip") or "Sem IP"
        icon = "🟢" if status == "ONLINE" else "🔴"
        if status == "ONLINE":
            online_count += 1
        lines.append(f"• {icon} {cam_name}: {status} (`{ip}`)")

    lines.append("")
    lines.append(f"📡 Uptime da Malha: **{online_count}/{total_count} câmeras ativas**.")
    lines.append("🛡️ *Notificações diárias silenciadas no ntfy para evitar fadiga de decisão.*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Gera o Relatório Semanal de CFTV e Conectividade")
    parser.add_argument("--days", type=int, default=7, help="Número de dias para análise (padrão: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Apenas exibe o relatório no terminal sem enviar ao ntfy")
    parser.add_argument("--force", action="store_true", help="Força envio para o ntfy mesmo fora de domingo")
    args = parser.parse_args()

    report_text = build_weekly_report(days=args.days)

    if args.dry_run:
        print("=== MODO DRY-RUN: Relatório Gerado ===")
        print(report_text)
        print("======================================")
        return

    # Se chamado sem dry-run, envia ao ntfy
    send_report_ntfy(
        title="CFTV: Relatório Semanal de Conectividade",
        message=report_text,
        priority="3",
        tags="calendar,camera,bar_chart"
    )


if __name__ == "__main__":
    main()
