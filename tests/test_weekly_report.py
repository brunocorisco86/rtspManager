"""
Testes unitários para o gerador de relatório semanal (generate_weekly_network_report)
"""

import sys
from pathlib import Path
from unittest.mock import patch
import pytest

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from generate_weekly_network_report import build_weekly_report, send_report_ntfy


def test_build_weekly_report_structure():
    mock_stats = {
        "available": True,
        "days": 7,
        "counts_by_type": {
            "IP_CHANGED": 5,
            "DISCONNECTED": 2,
            "RECONNECTED": 2,
            "DISCOVERED": 1
        },
        "ranking": [
            {
                "device_name": "Camera_04",
                "total_events": 7,
                "ip_changes": 5,
                "disconnects": 2,
                "reconnects": 2
            }
        ]
    }

    with patch("generate_weekly_network_report.get_weekly_stats", return_value=mock_stats):
        report = build_weekly_report(days=7)
        assert "Relatório Semanal CFTV & Rede" in report
        assert "Trocas de IP registradas: **5**" in report
        assert "Quedas/Desconexões: **2**" in report
        assert "Camera_04" in report
        assert "Uptime da Malha:" in report


def test_send_report_ntfy_mocked():
    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value.returncode = 0
        success = send_report_ntfy("Título Teste", "Corpo da Mensagem")
        assert success is True
