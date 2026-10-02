#!/usr/bin/env python3
"""
==============================================================================
CFTV Database Client - 10_RTSP_Manager
==============================================================================
Gerencia o registro e consulta de eventos de conectividade (trocas de IP,
desconexões, reconexões e descobertas de câmeras e NVR) no banco PostgreSQL
hospedado no nó Alpine (ssh alpine / 192.168.1.7).
==============================================================================
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

# PostgreSQL Connection Settings com fallback para o homelab padrão
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "192.168.1.7")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "brunoconter")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "blurbang")
POSTGRES_DB = os.getenv("POSTGRES_DB", "light_manager")

TABLE_NAME = "cftv_network_events"

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    try:
        import psycopg as psycopg2
        from psycopg.rows import dict_row as RealDictCursor
        PSYCOPG2_AVAILABLE = True
    except ImportError:
        PSYCOPG2_AVAILABLE = False


def get_connection():
    """Retorna uma conexão ativa com o banco PostgreSQL se disponível."""
    if not PSYCOPG2_AVAILABLE:
        return None
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            dbname=POSTGRES_DB,
            connect_timeout=3
        )
        return conn
    except Exception as e:
        # Não quebra os daemons se a rede estiver instável
        print(f"[CFTV_DB] Aviso: Não foi possível conectar ao Postgres ({POSTGRES_HOST}:{POSTGRES_PORT}): {e}", file=sys.stderr)
        return None


def init_db() -> bool:
    """Garante que a tabela e índices necessários existam no banco."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    device_name VARCHAR(100) NOT NULL,
                    device_type VARCHAR(50) NOT NULL,
                    mac_address VARCHAR(50),
                    event_type VARCHAR(50) NOT NULL,
                    old_ip VARCHAR(50),
                    new_ip VARCHAR(50),
                    details TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_cftv_events_timestamp ON {TABLE_NAME}(timestamp);
                CREATE INDEX IF NOT EXISTS idx_cftv_events_device ON {TABLE_NAME}(device_name);
                CREATE INDEX IF NOT EXISTS idx_cftv_events_type ON {TABLE_NAME}(event_type);
            """)
        conn.commit()
        return True
    except Exception as e:
        print(f"[CFTV_DB] Erro ao inicializar tabela {TABLE_NAME}: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        conn.close()


def record_event(
    device_name: str,
    device_type: str,
    event_type: str,
    old_ip: Optional[str] = None,
    new_ip: Optional[str] = None,
    mac_address: Optional[str] = None,
    details: Optional[str] = None,
    event_time: Optional[datetime] = None
) -> bool:
    """
    Registra um evento de conectividade no banco PostgreSQL.
    
    event_type: 'IP_CHANGED', 'DISCONNECTED', 'RECONNECTED', 'DISCOVERED'
    device_type: 'camera' | 'nvr'
    """
    conn = get_connection()
    if not conn:
        return False

    if event_time is None:
        event_time = datetime.now(timezone.utc)

    try:
        with conn.cursor() as cur:
            query = f"""
                INSERT INTO {TABLE_NAME} 
                (timestamp, device_name, device_type, mac_address, event_type, old_ip, new_ip, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(query, (
                event_time,
                device_name,
                device_type,
                mac_address,
                event_type,
                old_ip,
                new_ip,
                details
            ))
        conn.commit()
        return True
    except Exception as e:
        print(f"[CFTV_DB] Erro ao registrar evento {event_type} para {device_name}: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        conn.close()


def get_events(days: int = 7, limit: int = 200) -> List[Dict[str, Any]]:
    """Recupera eventos recentes do banco de dados."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor_factory = RealDictCursor if hasattr(psycopg2.extras, "RealDictCursor") else None
        with conn.cursor(cursor_factory=cursor_factory) as cur:
            cur.execute(f"""
                SELECT id, timestamp, device_name, device_type, mac_address, event_type, old_ip, new_ip, details
                FROM {TABLE_NAME}
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                ORDER BY timestamp DESC
                LIMIT %s
            """, (days, limit))
            rows = cur.fetchall()
            if cursor_factory:
                return [dict(r) for r in rows]
            else:
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        print(f"[CFTV_DB] Erro ao consultar eventos: {e}", file=sys.stderr)
        return []
    finally:
        conn.close()


def get_weekly_stats(days: int = 7) -> Dict[str, Any]:
    """
    Calcula agregados estatísticos dos últimos `days` dias:
    - Total de trocas de IP
    - Total de desconexões e reconexões
    - Câmeras com maior número de ocorrências (ranking de instabilidade)
    - Detalhamento de IP changes
    """
    conn = get_connection()
    if not conn:
        return {
            "available": False,
            "error": "Falha na conexão com o banco Postgres em alpine"
        }

    try:
        with conn.cursor() as cur:
            # 1. Total por tipo de evento
            cur.execute(f"""
                SELECT event_type, COUNT(*) 
                FROM {TABLE_NAME}
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                GROUP BY event_type
            """, (days,))
            counts_by_type = dict(cur.fetchall())

            # 2. Ranking de instabilidade por dispositivo (desconexões e trocas de IP)
            cur.execute(f"""
                SELECT device_name, 
                       COUNT(*) as total_events,
                       COUNT(*) FILTER (WHERE event_type = 'IP_CHANGED') as ip_changes,
                       COUNT(*) FILTER (WHERE event_type = 'DISCONNECTED') as disconnects,
                       COUNT(*) FILTER (WHERE event_type = 'RECONNECTED') as reconnects
                FROM {TABLE_NAME}
                WHERE timestamp >= NOW() - INTERVAL '%s days'
                GROUP BY device_name
                ORDER BY total_events DESC
                LIMIT 10
            """, (days,))
            ranking_cols = ["device_name", "total_events", "ip_changes", "disconnects", "reconnects"]
            ranking = [dict(zip(ranking_cols, row)) for row in cur.fetchall()]

            # 3. Lista das trocas de IP mais recentes
            cur.execute(f"""
                SELECT timestamp, device_name, old_ip, new_ip
                FROM {TABLE_NAME}
                WHERE timestamp >= NOW() - INTERVAL '%s days' AND event_type = 'IP_CHANGED'
                ORDER BY timestamp DESC
                LIMIT 15
            """, (days,))
            ip_changes = [
                {"timestamp": row[0], "device_name": row[1], "old_ip": row[2], "new_ip": row[3]}
                for row in cur.fetchall()
            ]

            return {
                "available": True,
                "days": days,
                "counts_by_type": counts_by_type,
                "ranking": ranking,
                "recent_ip_changes": ip_changes
            }
    except Exception as e:
        print(f"[CFTV_DB] Erro ao calcular estatísticas: {e}", file=sys.stderr)
        return {
            "available": False,
            "error": str(e)
        }
    finally:
        conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CFTV Database Client CLI")
    parser.add_argument("--record", action="store_true", help="Registra um evento no PostgreSQL")
    parser.add_argument("--device", help="Nome do dispositivo (ex: NVR_Principal, Camera_05)")
    parser.add_argument("--device-type", default="camera", choices=["camera", "nvr"], help="Tipo de dispositivo")
    parser.add_argument("--event", help="Tipo de evento: DISCONNECTED, RECONNECTED, IP_CHANGED, DISCOVERED")
    parser.add_argument("--old-ip", help="IP anterior")
    parser.add_argument("--new-ip", help="Novo IP")
    parser.add_argument("--mac", help="Endereço MAC")
    parser.add_argument("--details", help="Descrição detalhada do evento")
    parser.add_argument("--test", action="store_true", help="Executa autoteste de conectividade")

    args = parser.parse_args()

    if args.record:
        if not args.device or not args.event:
            print("Erro: --device e --event são obrigatórios com --record.", file=sys.stderr)
            sys.exit(1)
        ok = record_event(
            device_name=args.device,
            device_type=args.device_type,
            event_type=args.event,
            old_ip=args.old_ip,
            new_ip=args.new_ip,
            mac_address=args.mac,
            details=args.details
        )
        if ok:
            print(f"[CFTV_DB] Evento {args.event} para {args.device} gravado com sucesso.")
            sys.exit(0)
        else:
            print(f"[CFTV_DB] Falha ao gravar evento para {args.device}.", file=sys.stderr)
            sys.exit(1)

    if args.test or len(sys.argv) == 1:
        print(f"Testando conexão com {POSTGRES_HOST}:{POSTGRES_PORT} (DB: {POSTGRES_DB})...")
        if init_db():
            print("Tabela inicializada com sucesso!")
            stats = get_weekly_stats(7)
            print("Estatísticas obtidas:", stats.get("available"))
        else:
            print("Falha ao inicializar o banco.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
