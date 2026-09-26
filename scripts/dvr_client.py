#!/usr/bin/env python3
"""
dvr_client.py - Cliente assíncrono em Python puro para o protocolo DVRIP/NetSDK (porta 34567)
Usado em NVRs e Câmeras Xiongmai (XMeye / Sofia) sem qualquer modificação no firmware.
"""

import sys
import json
import struct
import socket
import asyncio
import hashlib
import logging

logger = logging.getLogger("dvr_client")

def sofia_hash(password: str = "") -> str:
    """Calcula o hash Sofia proprietário da Xiongmai a partir da senha."""
    if not password:
        return ""
    md5 = hashlib.md5(password.encode("utf-8")).digest()
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return "".join([chars[sum(x) % 62] for x in zip(md5[::2], md5[1::2])])

class DVRIPClient:
    """Cliente TCP assíncrono para protocolo Xiongmai DVRIP."""

    MSG_LOGIN_REQ = 1000
    MSG_LOGIN_RESP = 1001
    MSG_LOGOUT_REQ = 1002
    MSG_KEEPALIVE_REQ = 1006
    MSG_KEEPALIVE_RESP = 1007
    MSG_SYSINFO_REQ = 1020
    MSG_SYSINFO_RESP = 1021
    MSG_ALARM_SUB_REQ = 1500
    MSG_ALARM_SUB_RESP = 1501
    MSG_ALARM_INFO = 1504

    def __init__(self, host: str, port: int = 34567, user: str = "admin", password: str = ""):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.hash_pass = sofia_hash(password)
        self.session_id = 0
        self.seq = 0
        self.reader = None
        self.writer = None
        self.is_connected = False
        self.alarm_callback = None
        self._keepalive_task = None
        self._listener_task = None

    async def connect(self, timeout: float = 5.0) -> bool:
        """Abre conexão TCP com o NVR."""
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=timeout
            )
            self.is_connected = True
            logger.info(f"Conexão TCP estabelecida com {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Erro ao conectar a {self.host}:{self.port}: {e}")
            self.is_connected = False
            return False

    async def _send_packet(self, msg_id: int, payload_dict: dict) -> bool:
        """Empacota e envia uma mensagem DVRIP via TCP."""
        if not self.writer or self.writer.is_closing():
            return False
        try:
            payload_bytes = json.dumps(payload_dict).encode("utf-8") + b"\n\x00"
            length = len(payload_bytes)
            # Cabeçalho de 20 bytes do protocolo DVRIP:
            # Head (0xFF), Version (0), 2x Reservado, SessionID (uint32), Seq (uint32), 2x Reservado, MsgId (uint16), Length (uint32)
            header = struct.pack("<BB2xII2xHI", 0xFF, 0, self.session_id, self.seq, msg_id, length)
            self.writer.write(header + payload_bytes)
            await self.writer.drain()
            self.seq += 1
            return True
        except Exception as e:
            logger.error(f"Erro ao enviar pacote {msg_id}: {e}")
            return False

    async def _read_packet(self, timeout: float = 10.0):
        """Lê e desempacota uma mensagem DVRIP do socket."""
        if not self.reader:
            return None, None, None
        try:
            header_bytes = await asyncio.wait_for(self.reader.readexactly(20), timeout=timeout)
            head, version, session_id, seq, msg_id, len_data = struct.unpack("<BB2xII2xHI", header_bytes)
            if head != 0xFF:
                logger.warning(f"Cabeçalho inesperado: {hex(head)}")
                return None, None, None

            payload_bytes = await asyncio.wait_for(self.reader.readexactly(len_data), timeout=timeout)
            clean_str = payload_bytes.rstrip(b"\x00\n\r ").decode("utf-8", errors="ignore")
            try:
                data = json.loads(clean_str)
            except json.JSONDecodeError:
                data = {"raw": clean_str}

            return msg_id, session_id, data
        except asyncio.TimeoutError:
            return None, None, None
        except asyncio.IncompleteReadError:
            logger.warning("Conexão fechada pelo NVR (IncompleteRead).")
            self.is_connected = False
            return None, None, None
        except Exception as e:
            logger.error(f"Erro ao ler pacote: {e}")
            self.is_connected = False
            return None, None, None

    async def login(self) -> bool:
        """Autentica na sessão DVRIP."""
        if not self.is_connected:
            if not await self.connect():
                return False

        login_payload = {
            "EncryptType": "MD5",
            "LoginType": "DVRIP-Web",
            "PassWord": self.hash_pass,
            "UserName": self.user,
        }
        if not await self._send_packet(self.MSG_LOGIN_REQ, login_payload):
            return False

        msg_id, session_id, data = await self._read_packet(timeout=5.0)
        if data and data.get("Ret") == 100:
            self.session_id = int(data.get("SessionID", "0x0"), 16)
            logger.info(f"✅ Login autenticado no NVR com sucesso! SessionID: {hex(self.session_id)}")
            return True
        else:
            logger.error(f"❌ Falha no login: {data}")
            return False

    async def get_system_info(self) -> dict:
        """Obtém informações de hardware e firmware do NVR."""
        payload = {"Name": "SystemInfo"}
        if not await self._send_packet(self.MSG_SYSINFO_REQ, payload):
            return {}
        msg_id, _, data = await self._read_packet(timeout=5.0)
        return data.get("SystemInfo", {}) if data else {}

    async def subscribe_alarms(self, callback) -> bool:
        """Subscreve ao feed de alarmes e eventos em tempo real do NVR."""
        self.alarm_callback = callback
        payload = {"Name": "", "SessionID": hex(self.session_id)}
        if not await self._send_packet(self.MSG_ALARM_SUB_REQ, payload):
            return False

        msg_id, _, data = await self._read_packet(timeout=5.0)
        if data and data.get("Ret") == 100:
            logger.info("📡 Subscrição de alarmes (msgid 1500) confirmada pelo NVR!")
            return True
        logger.warning(f"Resposta inesperada na subscrição de alarmes: {data}")
        return False

    async def _keepalive_loop(self):
        """Envia keepalive a cada 20 segundos para manter a sessão ativa."""
        while self.is_connected:
            try:
                await asyncio.sleep(20)
                if self.is_connected:
                    await self._send_packet(self.MSG_KEEPALIVE_REQ, {"Name": "KeepAlive", "SessionID": hex(self.session_id)})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Exceção no keepalive: {e}")

    async def run_listener(self):
        """Loop contínuo de escuta para eventos assíncronos e alarmes."""
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        logger.info("Iniciando escuta ativa de eventos...")
        while self.is_connected:
            try:
                msg_id, session_id, data = await self._read_packet(timeout=30.0)
                if msg_id is None:
                    continue

                if msg_id == self.MSG_ALARM_INFO:
                    logger.debug(f"🚨 MSG_ALARM_INFO recebida: {data}")
                    if self.alarm_callback and callable(self.alarm_callback):
                        try:
                            # Chama o callback de forma assíncrona ou síncrona
                            res = self.alarm_callback(data)
                            if asyncio.iscoroutine(res):
                                asyncio.create_task(res)
                        except Exception as cb_err:
                            logger.error(f"Erro no callback de alarme: {cb_err}")

                elif msg_id == self.MSG_KEEPALIVE_RESP:
                    logger.debug("KeepAlive confirmado pelo NVR.")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Exceção no loop de escuta: {e}")
                break

        await self.close()

    async def close(self):
        """Encerra a conexão e tarefas associadas de forma limpa."""
        self.is_connected = False
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.reader = None
        self.writer = None
        logger.info("Conexão com NVR encerrada.")
