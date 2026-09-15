import sqlite3
import json

db_path = "/home/bruno/uptime-kuma-data/kuma.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Inserir Notificacao ntfy
ntfy_config = json.dumps({
    "ntfyserverurl": "https://ntfy.sh",
    "ntfytopic": "bruno-casa-dallas",
    "ntfyPriority": 4,
    "ntfyAuthenticationMethod": "none"
})

cur.execute("SELECT id FROM notification WHERE name = ?;", ("ntfy (bruno-casa-dallas)",))
row = cur.fetchone()
if not row:
    cur.execute(
        "INSERT INTO notification (name, active, user_id, is_default, config) VALUES (?, 1, 1, 1, ?);",
        ("ntfy (bruno-casa-dallas)", ntfy_config)
    )
    notif_id = cur.lastrowid
    print(f"Notificacao ntfy criada com ID: {notif_id}")
else:
    notif_id = row[0]
    print(f"Notificacao ntfy ja existe com ID: {notif_id}")

# 2. Lista de Monitores
monitors = [
    {"name": "Internet WAN (1.1.1.1)", "type": "ping", "hostname": "1.1.1.1", "port": None, "url": None, "interval": 60},
    {"name": "Roteador Gateway", "type": "ping", "hostname": "192.168.1.1", "port": None, "url": None, "interval": 60},
    {"name": "DNS Pi-hole (Alpine)", "type": "port", "hostname": "192.168.1.7", "port": 53, "url": None, "interval": 60},
    {"name": "PostgreSQL 15 (Alpine)", "type": "port", "hostname": "192.168.1.7", "port": 5432, "url": None, "interval": 60},
    {"name": "LightManager API (Alpine)", "type": "http", "hostname": None, "port": None, "url": "http://192.168.1.7:8000/docs", "interval": 60},
    {"name": "NVR Principal - RTSP", "type": "port", "hostname": "192.168.1.20", "port": 554, "url": None, "interval": 60},
    {"name": "NVR Principal - Web", "type": "http", "hostname": None, "port": None, "url": "http://192.168.1.20:80", "interval": 60},
    {"name": "go2rtc WebRTC (Peixe)", "type": "http", "hostname": None, "port": None, "url": "http://192.168.1.99:1984/", "interval": 60},
]

for m in monitors:
    cur.execute("SELECT id FROM monitor WHERE name = ?;", (m["name"],))
    exist = cur.fetchone()
    if not exist:
        cur.execute(
            """INSERT INTO monitor (name, active, user_id, interval, type, hostname, port, url, maxretries)
               VALUES (?, 1, 1, ?, ?, ?, ?, ?, 1);""",
            (m["name"], m["interval"], m["type"], m["hostname"], m["port"], m["url"])
        )
        mon_id = cur.lastrowid
        print(f"Monitor criado: {m['name']} (ID {mon_id})")
        
        # Vincula a notificacao ao monitor
        cur.execute(
            "INSERT INTO monitor_notification (monitor_id, notification_id) VALUES (?, ?);",
            (mon_id, notif_id)
        )
    else:
        print(f"Monitor ja existe: {m['name']}")

conn.commit()
conn.close()
print("Banco SQLite do Uptime Kuma atualizado com sucesso!")
