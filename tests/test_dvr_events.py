"""
Testes unitários para o módulo DVR Client, Event Listener e Gerador de Relatório PDF
"""

import sys
import sqlite3
import pytest
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from dvr_client import sofia_hash
from dvr_event_listener import EventDatabase, StorageManager
from generate_daily_report import query_daily_events, generate_timeseries_plot, generate_pdf_report

def test_sofia_hash():
    assert sofia_hash("") == ""
    # Teste de determinismo do hash
    h1 = sofia_hash("blurbang")
    assert isinstance(h1, str)
    assert len(h1) == 8
    assert sofia_hash("blurbang") == h1

def test_event_database(tmp_path):
    db_file = tmp_path / "test_events.db"
    db = EventDatabase(db_file)
    
    # Inserção
    db.record_event(
        channel_id=0,
        channel_name="Varanda (Canal 1)",
        event_type="HumanDetect",
        image_path=str(tmp_path / "frame1.jpg"),
        file_size=12345
    )
    
    today = datetime.now().strftime("%Y-%m-%d")
    events = query_daily_events(db_file, today)
    assert len(events) == 1
    assert events[0]["channel_id"] == 0
    assert events[0]["channel_name"] == "Varanda (Canal 1)"
    assert events[0]["event_type"] == "HumanDetect"
    assert events[0]["file_size"] == 12345

def test_report_generation(tmp_path):
    today = datetime.now().strftime("%Y-%m-%d")
    events = [
        {
            "id": 1,
            "timestamp": f"{today}T12:00:00",
            "date": today,
            "time": "12:00:00",
            "channel_id": 0,
            "channel_name": "Varanda (Canal 1)",
            "event_type": "HumanDetect",
            "image_path": str(tmp_path / "test.jpg"),
            "file_size": 50000
        }
    ]
    
    plot_file = tmp_path / "plot.png"
    assert generate_timeseries_plot(events, today, plot_file) is True
    assert plot_file.exists()
    assert plot_file.stat().st_size > 0
    
    pdf_file = tmp_path / "report.pdf"
    disk_info = {"free_gb": "4.0", "used_pct": "43%"}
    assert generate_pdf_report(events, today, plot_file, pdf_file, disk_info) is True
    assert pdf_file.exists()
    assert pdf_file.stat().st_size > 0
