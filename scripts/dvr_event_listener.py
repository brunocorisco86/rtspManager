#!/usr/bin/env python3
"""
dvr_event_listener.py - Daemon de escuta passiva de eventos do NVR Xiongmai.
Premissa de Ouro: Comunicação read-only, zero alterações no firmware/configurações do NVR.
- Escuta eventos (ex: HumanDetect / MotionDetect) via porta 34567.
- Captura snapshots instantâneos via go2rtc (nó Peixe :1984).
- Armazena no pendrive (/mnt/pendrive_cinza/cftv_events/) com metadados em SQLite.
- Dispara notificação push via ntfy (bruno-casa-dallas).
"""

import os
import sys
import time
import shutil
import sqlite3
import logging
import asyncio
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from dvr_client import DVRIPClient

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("dvr_listener")

# Configurações com fallback
NVR_HOST = os.getenv("NVR_HOST", "192.168.1.20")
NVR_PORT = int(os.getenv("NVR_PORT", "34567"))
NVR_USER = os.getenv("NVR_USER", "brunoconter")
NVR_PASS = os.getenv("NVR_PASS", "blurbang")

GO2RTC_HOST = os.getenv("GO2RTC_HOST", "192.168.1.99")
GO2RTC_PORT = int(os.getenv("GO2RTC_PORT", "1984"))

STORAGE_DIR = os.getenv("STORAGE_DIR", "/mnt/pendrive_cinza/cftv_events")
FALLBACK_STORAGE_DIR = os.path.expanduser("~/cftv_events")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "bruno-casa-dallas")

DEBOUNCE_SECONDS = int(os.getenv("DEBOUNCE_SECONDS", "45"))
MIN_FREE_SPACE_MB = int(os.getenv("MIN_FREE_SPACE_MB", "500"))

# Mapeamento de Canais para Nomes e Streams do go2rtc
CHANNEL_MAP = {
    0: {"name": "Varanda (Canal 1)", "stream": "canal_01"},
    1: {"name": "Frente (Canal 2)", "stream": "canal_02"},
    2: {"name": "Garagem (Canal 3)", "stream": "canal_03"},
    3: {"name": "Fundos (Canal 4)", "stream": "canal_04"},
    4: {"name": "Lateral (Canal 5)", "stream": "canal_05"},
    5: {"name": "Interna (Canal 6)", "stream": "canal_06"},
    # Fallback caso venha indexado de 1 a 6
    6: {"name": "Interna (Canal 6)", "stream": "canal_06"},
}

def resolve_storage_dir() -> Path:
    """Verifica se o pendrive está acessível; caso contrário usa o diretório de fallback."""
    p = Path(STORAGE_DIR)
    try:
        p.mkdir(parents=True, exist_ok=True)
        # Testa se é gravável
        test_file = p / ".write_test"
        test_file.touch()
        test_file.unlink()
        return p
    except Exception as e:
        logger.warning(f"Não foi possível gravar no pendrive ({STORAGE_DIR}): {e}. Usando fallback local.")
        fb = Path(FALLBACK_STORAGE_DIR)
        fb.mkdir(parents=True, exist_ok=True)
        return fb

class EventDatabase:
    """Gerenciador do banco de dados SQLite para registro de eventos."""
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    channel_id INTEGER NOT NULL,
                    channel_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    synced INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON events(date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_channel ON events(channel_id)")
            conn.commit()

    def record_event(self, channel_id: int, channel_name: str, event_type: str, image_path: str, file_size: int):
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        iso_str = now.isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (timestamp, date, time, channel_id, channel_name, event_type, image_path, file_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (iso_str, date_str, time_str, channel_id, channel_name, event_type, image_path, file_size))
            conn.commit()

class StorageManager:
    """Gerencia pastas diárias e política de rotação de disco (Garbage Collector)."""
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def get_today_dir(self) -> Path:
        today_dir = self.base_dir / datetime.now().strftime("%Y-%m-%d")
        today_dir.mkdir(parents=True, exist_ok=True)
        return today_dir

    def check_and_rotate_storage(self):
        """Remove pastas mais antigas se o espaço livre for inferior a MIN_FREE_SPACE_MB."""
        try:
            total, used, free = shutil.disk_usage(self.base_dir)
            free_mb = free // (1024 * 1024)
            if free_mb < MIN_FREE_SPACE_MB:
                logger.warning(f"Espaço livre no disco baixo: {free_mb} MB restantes. Iniciando rotação.")
                # Localiza pastas de datas YYYY-MM-DD
                subdirs = sorted([d for d in self.base_dir.iterdir() if d.is_dir() and d.name != "reports"])
                if subdirs:
                    oldest = subdirs[0]
                    logger.info(f"Removendo diretório de eventos antigo para liberar espaço: {oldest}")
                    shutil.rmtree(oldest, ignore_errors=True)
        except Exception as e:
            logger.error(f"Erro ao verificar rotação de armazenamento: {e}")

class NtfyNotifier:
    """Dispara alertas instantâneos via ntfy com imagem anexada."""
    def __init__(self, server: str, topic: str):
        self.url = f"{server.rstrip('/')}/{topic}"

    def send_alert(self, title: str, message: str, image_bytes: bytes, filename: str):
        headers = {
            "Title": title.encode("utf-8"),
            "Message": message.encode("utf-8"),
            "Filename": filename,
            "Priority": "high",
            "Tags": "warning,camera,bust_in_silhouette"
        }
        try:
            req = urllib.request.Request(self.url, data=image_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    logger.info(f"📱 Alerta ntfy enviado com sucesso para {self.url}")
                    return True
        except Exception as e:
            logger.error(f"Falha ao enviar alerta ntfy: {e}")
        return False

class DVREventOrchestrator:
    """Orquestrador principal de escuta, captura e registro."""
    def __init__(self):
        self.storage_path = resolve_storage_dir()
        self.db = EventDatabase(self.storage_path / "events.db")
        self.storage = StorageManager(self.storage_path)
        self.notifier = NtfyNotifier(NTFY_SERVER, NTFY_TOPIC)
        self.client = DVRIPClient(NVR_HOST, NVR_PORT, NVR_USER, NVR_PASS)
        self.cooldowns = {}  # {channel_id: timestamp_expiracao}

    def _fetch_frame_from_go2rtc(self, stream_name: str) -> bytes:
        url = f"http://{GO2RTC_HOST}:{GO2RTC_PORT}/api/frame.jpeg?src={stream_name}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    return resp.read()
        except Exception as e:
            logger.error(f"Erro ao capturar frame do go2rtc ({stream_name}): {e}")
        return b""

    async def handle_alarm_event(self, alarm_data: dict):
        """Processa o pacote AlarmInfo emitido pelo NVR."""
        try:
            # Estrutura típica Xiongmai:
            # {'Event': 'HumanDetect', 'Channel': 0, 'Status': 'Start', ...}
            # Ou {'Name': 'AlarmInfo', 'AlarmInfo': {...}}
            info = alarm_data
            if "AlarmInfo" in info:
                info = info["AlarmInfo"]

            event_type = info.get("Event", "Unknown")
            channel = info.get("Channel", 0)
            status = info.get("Status", "Start")

            # Filtramos apenas o início do evento de detecção de humano (ou alarme)
            if status.lower() not in ("start", "1", "true"):
                return

            # Verifica Cooldown para evitar enxurrada de disparos repetidos
            now = time.time()
            if channel in self.cooldowns and now < self.cooldowns[channel]:
                logger.debug(f"Canal {channel} em cooldown. Ignorando evento repetido.")
                return

            self.cooldowns[channel] = now + DEBOUNCE_SECONDS

            # Identifica canal e stream correspondente
            ch_info = CHANNEL_MAP.get(channel, {"name": f"Canal {channel+1}", "stream": f"canal_0{channel+1}"})
            ch_name = ch_info["name"]
            stream_name = ch_info["stream"]

            logger.info(f"🚨 DETECÇÃO DE PESSOA: {ch_name} | Tipo: {event_type}")

            # 1. Captura snapshot via go2rtc no nó Peixe
            frame_bytes = self._fetch_frame_from_go2rtc(stream_name)
            if not frame_bytes:
                logger.warning(f"Não foi possível obter frame para {stream_name}")
                return

            # 2. Grava no pendrive cinza com organização por dia
            today_dir = self.storage.get_today_dir()
            time_str = datetime.now().strftime("%H-%M-%S")
            filename = f"{time_str}_{stream_name}_{event_type.lower()}.jpg"
            file_path = today_dir / filename

            with open(file_path, "wb") as f:
                f.write(frame_bytes)

            file_size = len(frame_bytes)
            logger.info(f"💾 Snapshot gravado no pendrive: {file_path} ({file_size} bytes)")

            # 3. Registra no SQLite
            self.db.record_event(channel, ch_name, event_type, str(file_path), file_size)

            # 4. Dispara push instantâneo com foto para o smartphone via ntfy
            title = f"⚠️ Pessoa Identificada: {ch_name}"
            msg = f"Detecção registrada às {datetime.now().strftime('%H:%M:%S')}. Snapshot salvo com sucesso no pendrive."
            self.notifier.send_alert(title, msg, frame_bytes, filename)

            # 5. Verifica capacidade de armazenamento
            self.storage.check_and_rotate_storage()

        except Exception as e:
            logger.error(f"Erro ao processar evento de alarme: {e}", exc_info=True)

    async def start(self):
        """Inicia o daemon com auto-reconexão resiliente."""
        logger.info(f"Iniciando orquestrador de eventos CFTV em {self.storage_path}...")
        while True:
            try:
                if await self.client.login():
                    sys_info = await self.client.get_system_info()
                    hw = sys_info.get("HardWare", "Unknown")
                    logger.info(f"Conectado ao NVR Xiongmai ({hw}). Ativando subscrição de alarmes...")
                    
                    sub_ok = await self.client.subscribe_alarms(self.handle_alarm_event)
                    if sub_ok:
                        logger.info("📡 Escuta de alarmes ativa com sucesso!")
                        await self.client.run_listener()
                    else:
                        logger.warning("NVR não aceitou a subscrição. Tentando novamente em 15s...")
                else:
                    logger.warning(f"Falha de autenticação com NVR {NVR_HOST}. Tentando em 15s...")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro na conexão com NVR: {e}. Reconectando em 10s...")

            await asyncio.sleep(10)

def main():
    orchestrator = DVREventOrchestrator()
    try:
        asyncio.run(orchestrator.start())
    except KeyboardInterrupt:
        logger.info("Orquestrador encerrado pelo usuário.")

if __name__ == "__main__":
    main()
