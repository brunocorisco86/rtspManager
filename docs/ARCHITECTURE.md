# 🏛️ Arquitetura do Sistema: 10_RTSP_Manager

## 1. Visão Geral

O **10_RTSP_Manager** é uma solução de orquestração de vídeo, monitoramento de saúde de CFTV e gateway WebRTC de baixa latência, projetada especificamente para operar em hardware de recursos limitados (Raspberry Pi 3 Model B, 1 GB RAM, Alpine Linux).

```mermaid
flowchart TD
    subgraph LAN["Rede Local Residencial (192.168.1.0/24)"]
        subgraph CFTV["Parque de Câmeras & Gravador"]
            NVR["NVR Xiongmai (192.168.1.20)<br/>Portas 80, 554, 34567"]
            CAM1["Cam 04 (192.168.1.4)"]
            CAM2["Cam 05 (192.168.1.5)"]
            CAM3["Cam 06 (192.168.1.6)"]
            CAM4["Cam 10 (192.168.1.10)"]
            CAM5["Cam 11 (192.168.1.11)"]
            CAM6["Cam 31 (192.168.1.31)"]
        end

        subgraph PEIXE["Nó Peixe (192.168.1.99 | Alpine Linux)"]
            GO2RTC["go2rtc Engine<br/>WebRTC / HLS / MSE<br/>Porta 1984 / 8555<br/>Consumo: ~25 MB RAM"]
            WATCHDOG["CFTV Watchdog<br/>Port 554 & Ping Check"]
            SNAP["Snapshot Service<br/>HTTP Frame Extractor"]
        end
    end

    subgraph CLIENTS["Clientes e Destinos"]
        SMARTPHONE["Smartphone / Tablet<br/>(Navegador Web / PWA / WebRTC)"]
        NOTEBOOK["Notebook Bruno<br/>(Sem ActiveX / Sem Plugins)"]
        NTFY["ntfy.sh / bruno-casa-dallas<br/>(Notificações Push com Foto)"]
    end

    NVR -->|RTSP H.264| GO2RTC
    CAM1 & CAM2 & CAM3 & CAM4 & CAM5 & CAM6 -->|RTSP Passthrough| GO2RTC
    
    GO2RTC -->|WebRTC Latência 100ms| SMARTPHONE
    GO2RTC -->|WebRTC / MSE| NOTEBOOK
    
    WATCHDOG -.->|Checagem 554| NVR
    WATCHDOG -.->|Checagem 554| CAM1 & CAM2 & CAM3 & CAM4 & CAM5 & CAM6
    WATCHDOG -->|Alertas Push| NTFY
    SNAP -->|Envio de Foto| NTFY
```

---

## 2. Princípio Fundamental: Zero Transcoding (Modo Passthrough)

### O Problema da CPU no Raspberry Pi 3
* O processador Broadcom BCM2837 (4x Cortex-A53 @ 1.2 GHz) **não possui capacidade de transcodificar vídeo H.264/H.265 via software** para múltiplos canais sem travar e superaquecer o nó.
* Softwares pesados como MotionEye, Shinobi ou Frigate com detecção por CPU consomem 100% dos núcleos e esgotam o 1 GB de RAM.

### A Solução
* As câmeras já entregam os streams comprimidos em **H.264**.
* O **`go2rtc`** funciona como um proxy/multiplexador em memória:
  1. Conecta aos streams RTSP sob demanda.
  2. Reempacota os pacotes RTP nativos diretamente nos protocolos suportados pelos navegadores modernos (**WebRTC** e **MSE/HLS**).
  3. **Zero decodificação e zero recodificação de vídeo**: consumo de CPU permanece abaixo de **1 a 2%**, e a memória RAM não ultrapassa **30 MB**.

---

## 3. Matriz de Portas e Serviços

| Porta | Protocolo | Serviço / Função |
| :--- | :--- | :--- |
| `1984` | HTTP / WS | Painel Web do go2rtc, API REST, WebRTC signaling e snapshots |
| `8554` | RTSP | Servidor de re-streaming RTSP interno |
| `8555` | TCP / UDP | Transporte de mídia WebRTC (baixa latência) |
| `554` | RTSP | Portas de origem do NVR e Câmeras |

---

## 4. Estratégia de Deploy no Nó Peixe

Oferecemos duas abordagens compatíveis:
1. **Nativa via OpenRC (Recomendada para economia máxima):**
   * Binário estático compilado em Go executado como daemon do sistema Alpine (`/usr/local/bin/go2rtc`).
   * Sem overhead de containerização, gerenciado por `rc-service go2rtc start`.
2. **Container Docker Leve:**
   * Utilizando `alexxit/go2rtc:latest` com limites de memória configurados em 64 MB (`deploy.resources.limits.memory: 64M`).
