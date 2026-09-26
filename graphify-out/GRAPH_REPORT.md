# Graph Report - 10_RTSP_Manager  (2026-09-26)

## Corpus Check
- Corpus is ~7,471 words - fits in a single context window. You may not need a graph.

## Summary
- 52 nodes · 62 edges · 11 communities (7 shown, 4 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.85)
- Token cost: 1,200 input · 450 output

## Community Hubs (Navigation)
- Dynamic Resolver Core & ARP Resolution
- Homelab Watchdog & ntfy Alarms
- Resolver Unit Tests & YAML Generation
- RTSP Connectivity & Network Tests
- CFTV Cluster Topology & Issue Tracking
- Snapshot Capture & Image Utilities
- RTSP Probe & Port Diagnostics
- Legacy CFTV Watchdog
- Alpine Linux Host Installer
- Reconcile Daemon Service

## God Nodes (most connected - your core abstractions)
1. `Dynamic Resolver` - 12 edges
2. `main()` - 8 edges
3. `Homelab Watchdog` - 5 edges
4. `go2rtc Gateway` - 5 edges
5. `main()` - 4 edges
6. `normalize_mac()` - 4 edges
7. `get_arp_table()` - 4 edges
8. `generate_go2rtc_yaml()` - 4 edges
9. `check_port()` - 3 edges
10. `ping_host()` - 3 edges

## Surprising Connections (you probably didn't know these)
- `Dynamic Resolver` --reconfigures--> `go2rtc Gateway`  [EXTRACTED]
  scripts/dynamic_resolver.py → config/go2rtc.yaml
- `Homelab Watchdog` --validates_frames--> `go2rtc Gateway`  [EXTRACTED]
  scripts/homelab-watchdog.sh → config/go2rtc.yaml
- `test_normalize_mac()` --calls--> `normalize_mac()`  [INFERRED]
  tests/test_dynamic_resolver.py → scripts/dynamic_resolver.py
- `Camera Varanda (Canal 1)` --resolves--> `Issue #001 (Resolvida)`  [EXTRACTED]
  config/cameras.json → docs/ISSUES.md
- `Uptime Kuma` --dispatches_events--> `ntfy Alertas`  [EXTRACTED]
  docs/SESSIONS_2026-09-14.md → scripts/homelab-watchdog.sh

## Import Cycles
- None detected.

## Communities (11 total, 4 thin omitted)

### Community 0 - "Dynamic Resolver Core & ARP Resolution"
Cohesion: 0.24
Nodes (13): Dynamic Resolver, check_port(), get_arp_table(), main(), normalize_mac(), ping_host(), Solicita reload dos streams via API REST do go2rtc (se estiver em execução), Lê a tabela ARP do kernel (/proc/net/arp e ip neigh) Retorna mapeamentos: {mac:… (+5 more)

### Community 1 - "Homelab Watchdog & ntfy Alarms"
Cohesion: 0.47
Nodes (6): ntfy Alertas, Uptime Kuma, Homelab Watchdog, check_cftv_channel(), check_service(), homelab-watchdog.sh script

### Community 2 - "Resolver Unit Tests & YAML Generation"
Cohesion: 0.33
Nodes (5): generate_go2rtc_yaml(), Gera o arquivo go2rtc.yaml com base nos IPs e canais resolvidos dinamicamente, Testes unitários do Dynamic Resolver e Resolução por MAC Address, test_generate_go2rtc_yaml(), test_normalize_mac()

### Community 3 - "RTSP Connectivity & Network Tests"
Cohesion: 0.33
Nodes (3): Testes de conectividade e validação estrutural do 10_RTSP_Manager, Valida se o NVR está acessível na rede local, test_nvr_network_connectivity()

### Community 4 - "CFTV Cluster Topology & Issue Tracking"
Cohesion: 0.40
Nodes (5): 10_RTSP_Manager, Camera Varanda (Canal 1), Issue #001 (Resolvida), NVR Xiongmai Principal, go2rtc Gateway

### Community 5 - "Snapshot Capture & Image Utilities"
Cohesion: 0.70
Nodes (4): capture_via_ffmpeg(), capture_via_go2rtc(), main(), send_to_ntfy_curl()

## Knowledge Gaps
- **7 isolated node(s):** `cftv_watchdog.sh script`, `install_alpine.sh script`, `reconcile_daemon.sh script`, `10_RTSP_Manager`, `NVR Xiongmai Principal` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Dynamic Resolver` connect `Dynamic Resolver Core & ARP Resolution` to `Homelab Watchdog & ntfy Alarms`, `Resolver Unit Tests & YAML Generation`, `CFTV Cluster Topology & Issue Tracking`?**
  _High betweenness centrality (0.218) - this node is a cross-community bridge._
- **Why does `go2rtc Gateway` connect `CFTV Cluster Topology & Issue Tracking` to `Dynamic Resolver Core & ARP Resolution`, `Homelab Watchdog & ntfy Alarms`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **Why does `Homelab Watchdog` connect `Homelab Watchdog & ntfy Alarms` to `CFTV Cluster Topology & Issue Tracking`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **What connects `cftv_watchdog.sh script`, `install_alpine.sh script`, `reconcile_daemon.sh script` to the rest of the system?**
  _7 weakly-connected nodes found - possible documentation gaps or missing edges._