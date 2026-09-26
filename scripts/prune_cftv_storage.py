#!/usr/bin/env python3
"""
prune_cftv_storage.py - Política de Retenção e Higienização do Armazenamento CFTV.
Elimina diretórios diários de fotos e registros no SQLite com mais de X dias (padrão: 31 dias).
Premissa: Baixo consumo de I/O e CPU, liberando espaço físico no pendrive cinza.
"""

import os
import sys
import shutil
import sqlite3
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("cftv_prune")

STORAGE_DIR = os.getenv("STORAGE_DIR", "/mnt/pendrive_cinza/cftv_events")
FALLBACK_STORAGE_DIR = os.path.expanduser("~/cftv_events")
DEFAULT_RETENTION_DAYS = 31

def resolve_storage_dir(custom_path: str = None) -> Path:
    if custom_path:
        return Path(custom_path)
    p = Path(STORAGE_DIR)
    if p.exists():
        return p
    fb = Path(FALLBACK_STORAGE_DIR)
    return fb if fb.exists() else p

def prune_storage(base_dir: Path, max_days: int = DEFAULT_RETENTION_DAYS, dry_run: bool = False) -> dict:
    """
    Remove pastas de fotos YYYY-MM-DD com mais de max_days dias e
    remove as entradas correspondentes do events.db, executando VACUUM.
    """
    stats = {
        "cutoff_date": "",
        "dirs_removed": 0,
        "files_removed": 0,
        "bytes_freed": 0,
        "db_rows_deleted": 0
    }

    if not base_dir.exists():
        logger.warning(f"Diretório de armazenamento não encontrado: {base_dir}")
        return stats

    cutoff = datetime.now() - timedelta(days=max_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    stats["cutoff_date"] = cutoff_str
    logger.info(f"Iniciando prune em {base_dir} (fotos anteriores a {cutoff_str} serão eliminadas). Dry-run: {dry_run}")

    # 1. Varredura dos diretórios de data YYYY-MM-DD
    for item in base_dir.iterdir():
        if not item.is_dir() or item.name == "reports":
            continue

        # Verifica se o nome da pasta é uma data válida YYYY-MM-DD
        try:
            folder_date = datetime.strptime(item.name, "%Y-%m-%d")
        except ValueError:
            continue

        if folder_date < cutoff:
            # Calcula tamanho da pasta antes de apagar
            folder_bytes = 0
            folder_files = 0
            for root, _, files in os.walk(item):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        folder_bytes += os.path.getsize(fp)
                        folder_files += 1
                    except OSError:
                        pass

            if dry_run:
                logger.info(f"[DRY-RUN] Seria removida a pasta {item.name} ({folder_files} arquivos, {folder_bytes // 1024} KB)")
            else:
                try:
                    shutil.rmtree(item)
                    logger.info(f"🗑️ Pasta removida: {item.name} ({folder_files} fotos, {folder_bytes // 1024} KB liberados)")
                except Exception as e:
                    logger.error(f"Erro ao remover pasta {item}: {e}")

            stats["dirs_removed"] += 1
            stats["files_removed"] += folder_files
            stats["bytes_freed"] += folder_bytes

    # 2. Higienização do banco SQLite events.db
    db_path = base_dir / "events.db"
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM events WHERE date < ?", (cutoff_str,))
                rows_to_delete = cursor.fetchone()[0]

                if dry_run:
                    logger.info(f"[DRY-RUN] Seriam excluídos {rows_to_delete} registros do events.db")
                else:
                    if rows_to_delete > 0:
                        cursor.execute("DELETE FROM events WHERE date < ?", (cutoff_str,))
                        conn.commit()
                        logger.info(f"🧹 Excluídos {rows_to_delete} registros antigos do events.db.")
                        # Executa VACUUM para recuperar espaço em disco no pendrive
                        cursor.execute("VACUUM;")
                        conn.commit()
                        logger.info("⚡ VACUUM executado no SQLite para compactação de disco.")

                stats["db_rows_deleted"] = rows_to_delete
        except Exception as e:
            logger.error(f"Erro ao limpar banco SQLite ({db_path}): {e}")

    # Exibe resumo do espaço em disco atual
    try:
        total, used, free = shutil.disk_usage(base_dir)
        free_gb = round(free / (1024**3), 2)
        total_gb = round(total / (1024**3), 2)
        logger.info(f"Espaço atual no pendrive: {free_gb} GB livres de {total_gb} GB totais.")
    except Exception:
        pass

    return stats

def main():
    parser = argparse.ArgumentParser(description="Prune de fotos de CFTV com mais de 31 dias")
    parser.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS, help="Número de dias de retenção (padrão: 31)")
    parser.add_argument("--dir", help="Caminho personalizado do diretório de armazenamento")
    parser.add_argument("--dry-run", action="store_true", help="Simula a remoção sem apagar arquivos")
    args = parser.parse_args()

    target_dir = resolve_storage_dir(args.dir)
    prune_storage(target_dir, max_days=args.days, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
