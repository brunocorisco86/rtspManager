"""
Testes unitários e de integração do módulo cftv_db e persistência no PostgreSQL
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from cftv_db import record_event, get_weekly_stats, get_events, init_db


def test_init_db_mocked():
    with patch("cftv_db.get_connection") as mock_conn:
        mock_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_instance.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.return_value = mock_instance

        success = init_db()
        assert success is True
        mock_cursor.execute.assert_called_once()
        mock_instance.commit.assert_called_once()


def test_record_event_mocked():
    with patch("cftv_db.get_connection") as mock_conn:
        mock_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_instance.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.return_value = mock_instance

        success = record_event(
            device_name="TestCam",
            device_type="camera",
            event_type="IP_CHANGED",
            old_ip="192.168.1.10",
            new_ip="192.168.1.50",
            mac_address="aa:bb:cc:dd:ee:ff",
            details="DHCP lease renewal"
        )
        assert success is True
        mock_cursor.execute.assert_called_once()
        mock_instance.commit.assert_called_once()


def test_get_weekly_stats_mocked():
    with patch("cftv_db.get_connection") as mock_conn:
        mock_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [
            [("IP_CHANGED", 3), ("DISCONNECTED", 1)], # counts_by_type
            [("TestCam", 4, 3, 1, 0)],                # ranking
            [(None, "TestCam", "192.168.1.10", "192.168.1.50")] # recent_ip_changes
        ]
        mock_instance.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.return_value = mock_instance

        stats = get_weekly_stats(days=7)
        assert stats["available"] is True
        assert stats["counts_by_type"]["IP_CHANGED"] == 3
        assert stats["ranking"][0]["device_name"] == "TestCam"
