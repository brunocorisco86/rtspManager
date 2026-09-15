# 📋 Plano de Desenvolvimento: 10_RTSP_Manager

Este documento define o roteiro de execução por etapas para validar, desenvolver e implantar o gerenciador de CFTV no nó **Peixe**.

---

## 🎯 Roteiro de Implementação em 4 Fases

```mermaid
flowchart LR
    F1["Fase 1<br/>Validação & URLs"] --> F2["Fase 2<br/>Deploy go2rtc no Peixe"]
    F2 --> F3["Fase 3<br/>Snapshots & ntfy"]
    F3 --> F4["Fase 4<br/>Acesso Remoto & Dashboard"]
```

---

### 🔹 Fase 1: Validação de Credenciais e Mapeamento de URLs RTSP
* **Objetivo:** Descobrir as credenciais exatas e os canais de vídeo que o NVR (`192.168.1.20`) e as câmeras aceitam.
* **Ações:**
  1. Configurar o `.env` local com a senha de administrador do NVR (definida na interface ou no monitor HDMI).
  2. Executar o script de teste `scripts/rtsp_probe.py` para testar os formatos:
     * `rtsp://user:pass@192.168.1.20:554/user=admin&password=SENHA&channel=1&stream=0.sdp`
     * `rtsp://user:pass@192.168.1.20:554/cam/realmonitor?channel=1&subtype=0`
  3. Mapear os 6 canais do NVR correspondentes às localizações físicas (Frente, Fundos, Lateral, Portão, etc.).

---

### 🔹 Fase 2: Implantação do Engine go2rtc no Nó Peixe (Go-Live)
* **Objetivo:** Subir o gateway de vídeo leve com consumo < 30 MB RAM no Raspberry Pi 3.
* **Ações:**
  1. Transferir o arquivo de configuração [`config/go2rtc.yaml`](file:///home/brunoconter/Documentos/4_HOMELAB/10_RTSP_Manager/config/go2rtc.yaml) para o nó Peixe (`/etc/go2rtc/go2rtc.yaml`).
  2. Executar o instalador nativo [`scripts/install_alpine.sh`](file:///home/brunoconter/Documentos/4_HOMELAB/10_RTSP_Manager/scripts/install_alpine.sh).
  3. Iniciar o serviço OpenRC:
     ```bash
     rc-service go2rtc start
     rc-update add go2rtc default
     ```
  4. Testar a interface web no navegador através de `http://192.168.1.99:1984` e validar o streaming via WebRTC sem plugins.

---

### 🔹 Fase 3: Automação de Snapshots e Alertas no Celular (ntfy)
* **Objetivo:** Disparar fotos no smartphone em caso de eventos ou requisições.
* **Ações:**
  1. Integrar o [`scripts/capture_snapshot.py`](file:///home/brunoconter/Documentos/4_HOMELAB/10_RTSP_Manager/scripts/capture_snapshot.py) para extrair frames diretamente da API do go2rtc (`/api/frame.jpeg?src=...`).
  2. Configurar o envio automático da foto para o canal `bruno-casa-dallas` do **ntfy**.
  3. Integrar com o cron job para relatório fotográfico diário ou acionamento sob demanda.

---

### 🔹 Fase 4: Acesso Remoto Seguro e Painel Unificado
* **Objetivo:** Visualizar as câmeras fora de casa sem abrir portas no roteador.
* **Ações:**
  1. Aproveitar o **Tailscale Subnet Router** que já está em produção no nó Peixe (`100.88.42.19`).
  2. Acessar `http://192.168.1.99:1984` pelo celular ou notebook conectado na Tailnet, de qualquer lugar do mundo, com transmissão segura e criptografada via WireGuard.
