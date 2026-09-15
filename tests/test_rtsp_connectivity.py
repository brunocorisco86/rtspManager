"""
Testes de conectividade e validação estrutural do 10_RTSP_Manager
"""

import json
import socket
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

def test_cameras_json_structure():
    config_file = BASE_DIR / "config" / "cameras.json"
    assert config_file.exists(), "cameras.json deve existir"
    
    with open(config_file, "r") as f:
        data = json.load(f)
        
    assert "nvr" in data
    assert "cameras" in data
    assert len(data["cameras"]) == 6
    assert data["nvr"]["ip"] == "192.168.1.20"

def test_go2rtc_yaml_exists():
    yaml_file = BASE_DIR / "config" / "go2rtc.yaml"
    assert yaml_file.exists(), "go2rtc.yaml deve existir"
    content = yaml_file.read_text()
    assert "streams:" in content
    assert "192.168.1.20" in content

def test_nvr_network_connectivity():
    """Valida se o NVR está acessível na rede local"""
    nvr_ip = "192.168.1.20"
    with socket.create_connection((nvr_ip, 554), timeout=2.0) as s:
        assert s is not None
