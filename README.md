# 📹 10_RTSP_Manager

**Gateway de Streaming CFTV em WebRTC com Resolução Dinâmica por MAC Address e Autodescoberta**  
*Desenvolvido para o cluster Homelab (Nó Peixe - Raspberry Pi 3 / Alpine Linux).*

---

## 📌 Principais Diferenciais e Arquitetura Resiliente

1. **Resiliência Total a DHCP (Identidade por MAC Address):**
   * Em redes domésticas sem IP estático configurado em cada câmera, o DHCP do roteador pode alterar os IPs após reboots.
   * O **10_RTSP_Manager** usa o **MAC Address como Identificador Único Universal (SSOT)**.
   * Se o IP de uma câmera mudar (ex: `192.168.1.4` -> `192.168.1.18`), o sistema detecta a mudança via tabela ARP do kernel, atualiza a stream do `go2rtc` dinamicamente e envia um alerta push no celular via **ntfy** (`bruno-casa-dallas`).
2. **Entrada Flexível de Dispositivos:**
   * Você pode cadastrar o NVR e as câmeras em `config/cameras.json` informando **apenas o MAC**, **apenas o IP**, ou **ambos**.
   * Se você informar apenas o IP, o sistema aprende e grava o MAC automaticamente na primeira varredura.
3. **Autodescoberta de Câmeras Plugadas (Hot-Plug):**
   * O resolvedor varre a rede local e, se identificar qualquer nova câmera com porta RTSP `554` aberta, cataloga o novo canal e notifica no seu smartphone.
4. **Zero Transcoding (Otimizado para Raspberry Pi 3 / 1 GB RAM):**
   * O motor **go2rtc** opera em modo **passthrough**, reempacotando pacotes H.264 diretamente em WebRTC sem transcodificação por CPU.
   * **Consumo de recursos no nó Peixe:** **~25 MB de RAM** e **< 1% de CPU**.

---

## 🌐 Parque de CFTV Mapeado

| Dispositivo | MAC Address (SSOT) | IP Atual | Portas | Status |
| :--- | :--- | :--- | :--- | :--- |
| **NVR Principal** | `00:12:43:24:4e:c6` | `192.168.1.20` | `80`, `554`, `34567` | ONLINE ✅ |
| **Camera Varanda (Canal 1)** | `d4:a3:eb:89:bd:f4` | `192.168.1.16` | `80`, `554`, `8899`, `34567` | ONLINE ✅ |
| **Camera Frente** | `a4:ef:15:30:79:32` | `192.168.1.4` | `80`, `554`, `34567` | ONLINE ✅ |
| **Camera Fundos** | `c4:3c:b0:79:80:db` | `192.168.1.5` | `80`, `554`, `34567` | ONLINE ✅ |
| **Camera Lateral** | `48:8f:4c:3d:13:14` | `192.168.1.6` | `80`, `554`, `34567` | ONLINE ✅ |
| **Camera Garagem** | `38:be:ab:91:96:85` | `192.168.1.10` | `80`, `554`, `34567` | ONLINE ✅ |
| **Camera Portao** | `38:be:ab:91:96:85` | `192.168.1.10` | `80`, `554`, `34567` | ONLINE ✅ |
| **Camera Interna** | `00:13:00:01:61:7b` | `192.168.1.31` | `80`, `554`, `8899` | ONLINE ✅ |

> [!TIP]
> **Canal 01 Restabelecido:** O Canal 01 foi integrado diretamente com a câmera Dual-Lens da Varanda (`192.168.1.16:554`), com resolução 2.5K HEVC nativo e helper H.264 para navegadores. A Issue #001 foi resolvida. Consulte [`docs/ISSUES.md`](file:///home/brunoconter/Documentos/4_HOMELAB/10_RTSP_Manager/docs/ISSUES.md).

---

## ⚙️ Como Cadastrar Câmeras em `config/cameras.json`

Você tem total liberdade para cadastrar por MAC, por IP, ou ambos:

```json
{
  "name": "Camera_Frente",
  "mac": "a4:ef:15:30:79:32",   // Opcional se tiver IP (recomendado para resiliência)
  "ip": "192.168.1.4",          // Opcional se tiver MAC (usado como fallback)
  "nvr_channel": 1,
  "user": "admin",
  "password": ""
}
```

---

## 🚀 Como Executar o Dynamic Resolver

### 1. Execução Manual de Reconciliação
```bash
python3 scripts/dynamic_resolver.py
```
O script irá:
1. Varrer o cache ARP do kernel.
2. Resolver os IPs atuais de cada MAC.
3. Notificar via `ntfy` caso algum IP tenha mudado ou nova câmera tenha sido encontrada.
4. Salvar o estado em [`config/inventory.json`](file:///home/brunoconter/Documentos/4_HOMELAB/10_RTSP_Manager/config/inventory.json).
5. Gerar automaticamente o [`config/go2rtc.yaml`](file:///home/brunoconter/Documentos/4_HOMELAB/10_RTSP_Manager/config/go2rtc.yaml).
6. Solicitar hot-reload ao `go2rtc` sem derrubar os demais canais.

### 2. Execução Contínua em Background (Daemon)
```bash
# Executa a reconciliação a cada 5 minutos (300 segundos):
./scripts/reconcile_daemon.sh 300
```

---

## 🚢 Como Implantar no Nó Peixe (`ssh peixe`)

1. Copie o projeto para o nó Peixe:
   ```bash
   scp -r ~/Doc/4/10_RTSP_Manager peixe:/home/bruno/
   ```
2. Instale o go2rtc nativo no Alpine:
   ```bash
   ssh peixe
   cd /home/bruno/10_RTSP_Manager
   chmod +x scripts/*.sh scripts/*.py
   ./scripts/install_alpine.sh
   rc-service go2rtc start
   rc-update add go2rtc default
   ```
3. Adicione o daemon no crontab do Peixe para auto-reconciliação a cada 5 minutos:
   ```bash
   crontab -e
   # Adicione a linha:
   # */5 * * * * python3 /home/bruno/10_RTSP_Manager/scripts/dynamic_resolver.py > /dev/null 2>&1
   ```
4. Abra o painel WebRTC no navegador:
   * **Local:** `http://192.168.1.99:1984`
   * **Remoto seguro via Tailnet:** `http://100.88.42.19:1984`

---

## 🧪 Testes Automatizados

```bash
pytest tests/
```
Valida a normalização de MACs, leitura da tabela ARP, integridade dos schemas JSON, protocolo Sofia hash e geração do relatório executivo em PDF.

---

## 🛡️ Eventos Inteligentes & Relatório Noturno Diário (Zero-Touch NVR)

O sistema conta com um orquestrador passivo de eventos conectado ao NVR na porta `34567` (DVRIP):
* **Escuta Passiva (`scripts/dvr_event_listener.py`):** Serviço OpenRC no nó Alpine (`cftv-events`). Captura detecções de humanos e salva snapshots no pendrive cinza (`/mnt/pendrive_cinza/cftv_events/`).
* **Alerta Instantâneo:** Envia push com foto no app **ntfy** (`bruno-casa-dallas`) com cooldown anti-duplicação.
* **Relatório Noturno às 21:00 (`scripts/generate_daily_report.py`):** Cron diário que compila gráfico de série temporal (Matplotlib) e documento executivo em PDF (ReportLab) com as fotos das pessoas detectadas, despachando direto para o smartphone.
* **Política de Prune e Higienização (`scripts/prune_cftv_storage.py`):** Elimina automaticamente fotos e pastas com mais de 31 dias, limpando o banco SQLite e executando `VACUUM` para liberar espaço físico no pendrive cinza.


