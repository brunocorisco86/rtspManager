# 📹 10_RTSP_Manager

**Gateway de Streaming CFTV em WebRTC, Monitoramento de Câmeras e Alertas de Snapshot**  
*Desenvolvido para o cluster Homelab (Nó Peixe - Raspberry Pi 3 / Alpine Linux).*

---

## 📌 Contexto e Propósito

Este projeto integra o sistema de CFTV residencial — composto por um **NVR Xiongmai Linux (`192.168.1.20`)** e **6 Câmeras IP RTSP** — ao ecossistema do homelab, resolvendo limitações crônicas de gravadores chineses:

1. **Eliminação de Plugins Legados:** Câmeras e NVRs Xiongmai geralmente dependem de plugins ActiveX (`.ocx`) incompatíveis com smartphones e navegadores modernos. O `10_RTSP_Manager` converte os streams RTSP nativamente em **WebRTC** e **HLS/MSE** sem necessidade de plugins.
2. **Zero Transcoding (Otimizado para Raspberry Pi 3):** O nó de produção **Peixe** possui 1 GB de RAM. A arquitetura opera em modo **passthrough**, reempacotando pacotes RTP com consumo de **~25 MB de RAM** e **< 1% de CPU**.
3. **Monitoramento Ativo de Falhas:** Watchdog dedicado que valida a disponibilidade do NVR e de cada uma das câmeras, disparando alertas push no aplicativo **ntfy** (`bruno-casa-dallas`).
4. **Captura de Snapshots:** Extração de frames JPEG sob demanda para envio de fotos diretamente para o celular.

---

## 🌐 Mapeamento do Parque de CFTV

| Dispositivo | Endereço IP | Portas Abertas | Protocolo / Papel |
| :--- | :--- | :--- | :--- |
| **NVR Central** | `192.168.1.20` | `80` (HTTP), `554` (RTSP), `34567` (XM) | Gravador central multi-canal Xiongmai |
| **Câmera 01** | `192.168.1.4` | `80` (HTTP), `554` (RTSP), `34567` (XM) | Stream H.264 individual |
| **Câmera 02** | `192.168.1.5` | `80` (HTTP), `554` (RTSP), `34567` (XM) | Stream H.264 individual |
| **Câmera 03** | `192.168.1.6` | `80` (HTTP), `554` (RTSP), `34567` (XM) | Stream H.264 individual |
| **Câmera 04** | `192.168.1.10` | `80` (HTTP), `554` (RTSP), `34567` (XM) | Stream H.264 individual |
| **Câmera 05** | `192.168.1.11` | `80` (HTTP), `554` (RTSP), `34567` (XM) | Stream H.264 individual |
| **Câmera 06** | `192.168.1.31` | `80` (HTTP), `554` (RTSP), `8899` (ONVIF) | Stream H.264 / ONVIF |

---

## 📂 Estrutura do Repositório

```text
10_RTSP_Manager/
├── .gitignore              # Ignora ambientes virtuais, credenciais e logs
├── .env.example            # Modelo de variáveis de ambiente
├── docker-compose.yml      # Opção de deploy declarativo em container leve
├── README.md               # Este documento
├── config/
│   ├── cameras.json        # Catálogo com IPs, portas e formatos de URL
│   └── go2rtc.yaml         # Configuração de streams e portas do go2rtc
├── docs/
│   ├── ARCHITECTURE.md     # Detalhamento de arquitetura, fluxo e passthrough
│   └── DEVELOPMENT_PLAN.md # Roteiro de desenvolvimento em 4 fases
├── scripts/
│   ├── install_alpine.sh   # Instalador nativo do go2rtc como serviço OpenRC
│   ├── rtsp_probe.py       # Validador de streams, codecs e credenciais RTSP
│   ├── capture_snapshot.py # Utilitário para captura de frames e envio ao ntfy
│   └── cftv_watchdog.sh    # Watchdog que notifica queda de câmeras no celular
└── tests/
    └── test_rtsp_connectivity.py # Testes de validação de configuração e rede
```

---

## 🚀 Como Testar Localmente na sua Máquina

### 1. Clonar / Acessar a pasta
```bash
cd ~/Doc/4/10_RTSP_Manager
```

### 2. Configurar Variáveis
```bash
cp .env.example .env
# Edite com suas credenciais do NVR se houver:
# nano .env
```

### 3. Diagnosticar as Câmeras e Portas
```bash
python3 scripts/rtsp_probe.py
```

### 4. Executar Testes Estruturais
```bash
pytest tests/
```

---

## 🚢 Como Implantar no Nó Peixe (`ssh peixe`)

### Opção A: Instalação Nativa via OpenRC (Recomendada - Consumo Mínimo de ~20 MB)
1. Envie a configuração e o script de instalação para o nó Peixe:
   ```bash
   scp config/go2rtc.yaml peixe:/etc/go2rtc/go2rtc.yaml
   scp scripts/install_alpine.sh peixe:/tmp/install_alpine.sh
   ```
2. Conecte no nó Peixe e execute:
   ```bash
   ssh peixe
   chmod +x /tmp/install_alpine.sh && /tmp/install_alpine.sh
   rc-service go2rtc start
   rc-update add go2rtc default
   ```
3. Acesse a interface Web no navegador:
   * **URL Local:** `http://192.168.1.99:1984`
   * **Acesso Remoto Seguro:** Conecte o celular na Tailnet e acerte `http://100.88.42.19:1984`.

### Opção B: Deploy via Docker
```bash
scp -r ~/Doc/4/10_RTSP_Manager peixe:/home/bruno/
ssh peixe "cd /home/bruno/10_RTSP_Manager && docker compose up -d"
```

---

## 📸 Testando Snapshots e Notificações com Foto

Você pode extrair uma foto instantânea de qualquer câmera e disparar para o seu celular pelo **ntfy**:

```bash
# Captura via go2rtc e envia foto com push para bruno-casa-dallas:
python3 scripts/capture_snapshot.py --src nvr_canal1 --ntfy --title "Portão Frente 📸"
```

---

## 📚 Documentações Complementares
* [Arquitetura Detalhada e Passthrough](docs/ARCHITECTURE.md)
* [Plano de Desenvolvimento em Fases](docs/DEVELOPMENT_PLAN.md)
