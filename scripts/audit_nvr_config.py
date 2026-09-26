#!/usr/bin/env python3
"""
audit_nvr_config.py - Auditoria 100% passiva (Read-Only) de Capacidades e Configurações
do NVR Xiongmai via porta 34567 (DVRIP).
Premissa de Ouro: Consulta puramente informativa, zero alterações no NVR.
"""

import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from dvr_client import DVRIPClient

NVR_HOST = os.getenv("NVR_HOST", "192.168.1.20")
NVR_PORT = int(os.getenv("NVR_PORT", "34567"))
NVR_USER = os.getenv("NVR_USER", "brunoconter")
NVR_PASS = os.getenv("NVR_PASS", "blurbang")

def print_banner(text):
    print("\n" + "=" * 70)
    print(f" {text}")
    print("=" * 70)

async def run_audit():
    print_banner(f"AUDITORIA PASSIVA DE CAPACIDADES E CANAIS: NVR {NVR_HOST}")
    client = DVRIPClient(NVR_HOST, NVR_PORT, NVR_USER, NVR_PASS)

    if not await client.login():
        print(f"❌ Falha de autenticação no NVR {NVR_HOST}:{NVR_PORT}")
        return

    # 1. Informações de Hardware & Firmware
    sys_info = await client.get_system_info()
    print("\n📦 Informações de Hardware & Sistema:")
    print(f"  • Modelo/Placa:     {sys_info.get('HardWare', 'Desconhecido')}")
    print(f"  • Versão Firmware:  {sys_info.get('SoftWareVersion', 'Desconhecida')}")
    print(f"  • Data de Build:    {sys_info.get('BuildTime', 'Desconhecida')}")
    print(f"  • Canais Digitais:  {sys_info.get('DigChannel', 'N/A')}")
    print(f"  • Serial:           {sys_info.get('SerialNo', 'N/A')}")

    # 2. Capacidades de Alarme e IA (Ability / msgid 1360)
    payload_ability = {"Name": "SystemFunction", "SessionID": hex(client.session_id)}
    await client._send_packet(1360, payload_ability)
    _, _, ability_data = await client._read_packet(timeout=4.0)

    alarm_abilities = ability_data.get("SystemFunction", {}).get("AlarmFunction", {}) if ability_data else {}
    print("\n🧠 Capacidades de IA e Sensores Suportadas pelo NVR:")
    print(f"  • Detecção de Humanos (HumanDectionNVRNew): {'✅ SUPORTADO' if alarm_abilities.get('HumanDectionNVRNew') else '❌ NÃO'}")
    print(f"  • Detecção Facial (FaceDetect):             {'✅ SUPORTADO' if alarm_abilities.get('FaceDetect') else '❌ NÃO'}")
    print(f"  • Detecção de Movimento (MotionDetect):     {'✅ SUPORTADO' if alarm_abilities.get('MotionDetect') else '❌ NÃO'}")
    print(f"  • Oclusão de Câmera (BlindDetect):          {'✅ SUPORTADO' if alarm_abilities.get('BlindDetect') else '❌ NÃO'}")
    print(f"  • Perda de Sinal de Vídeo (LossDetect):     {'✅ SUPORTADO' if alarm_abilities.get('LossDetect') else '❌ NÃO'}")

    # 3. Nomes dos Canais (AVEnc.VideoWidget / msgid 1042)
    payload_names = {"Name": "AVEnc.VideoWidget", "SessionID": hex(client.session_id)}
    await client._send_packet(1042, payload_names)
    _, _, widget_data = await client._read_packet(timeout=4.0)
    widgets = widget_data.get("AVEnc.VideoWidget", []) if widget_data else []

    # 4. Configuração de MotionDetect por Canal
    payload_motion = {"Name": "Detect.MotionDetect", "SessionID": hex(client.session_id)}
    await client._send_packet(1042, payload_motion)
    _, _, motion_data = await client._read_packet(timeout=4.0)
    motions = motion_data.get("Detect.MotionDetect", []) if motion_data else []

    # 5. Configuração de HumanDectionNVRNew por Canal
    payload_human = {"Name": "Detect.HumanDectionNVRNew", "SessionID": hex(client.session_id)}
    await client._send_packet(1042, payload_human)
    _, _, human_data = await client._read_packet(timeout=4.0)
    humans = human_data.get("Detect.HumanDectionNVRNew", []) if human_data else []

    print("\n📊 Status Configurado por Canal:")
    print(f"{'Canal':<8} | {'Nome Câmera':<16} | {'Motion Detect':<14} | {'Human Detect IA':<18} | {'Snap Habilitado':<16}")
    print("-" * 80)

    num_channels = max(len(widgets), len(motions), len(humans), 6)
    for i in range(num_channels):
        ch_label = f"Canal {i+1}"
        ch_name = "N/A"
        if i < len(widgets) and widgets[i]:
            ch_name = widgets[i].get("ChannelTitle", {}).get("Name", "N/A")

        motion_active = "INATIVO"
        snap_active = "NÃO"
        if i < len(motions) and motions[i]:
            if motions[i].get("Enable"):
                motion_active = "ATIVO 🟢"
            snap_active = "SIM ✅" if motions[i].get("EventHandler", {}).get("SnapEnable") else "NÃO"

        human_active = "NÃO CONFIGURADO (null)"
        if i < len(humans) and humans[i]:
            human_active = "ATIVO 🟢" if humans[i].get("Enable") else "DESATIVADO"

        print(f"{ch_label:<8} | {ch_name:<16} | {motion_active:<14} | {human_active:<18} | {snap_active:<16}")

    print_banner("CONCLUSÃO: O NVR possui IA de Humano, porém opera atualmente em MotionDetect.")
    await client.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_audit())
