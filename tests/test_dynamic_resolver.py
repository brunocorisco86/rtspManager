"""
Testes unitários do Dynamic Resolver e Resolução por MAC Address
"""

import pytest
from pathlib import Path
import sys

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from dynamic_resolver import normalize_mac, generate_go2rtc_yaml

def test_normalize_mac():
    assert normalize_mac("00:12:43:24:4e:c6") == "00:12:43:24:4e:c6"
    assert normalize_mac("001243244EC6") == "00:12:43:24:4e:c6"
    assert normalize_mac("00-12-43-24-4E-C6") == "00:12:43:24:4e:c6"
    assert normalize_mac(None) is None

def test_generate_go2rtc_yaml():
    nvr = {
        "name": "NVR_Test",
        "resolved_ip": "192.168.1.20",
        "user": "admin",
        "password": ""
    }
    cameras = [
        {
            "name": "Cam_Frente",
            "resolved_ip": "192.168.1.4",
            "status": "ONLINE",
            "user": "admin",
            "password": ""
        },
        {
            "name": "Cam_Offline",
            "resolved_ip": None,
            "status": "OFFLINE",
            "user": "admin",
            "password": ""
        }
    ]
    yaml_text = generate_go2rtc_yaml(nvr, cameras)
    assert "api:" in yaml_text
    assert "rtsp:" in yaml_text
    assert "nvr_canal1:" in yaml_text
    assert "192.168.1.20" in yaml_text
    assert "cam_frente:" in yaml_text
    assert "192.168.1.4" in yaml_text
    # Câmera offline não deve ser gerada no stream direto
    assert "cam_offline:" not in yaml_text
