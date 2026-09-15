# 📖 Playbook de Go-Live: 10_RTSP_Manager no Nó Peixe

Este playbook é o guia operacional definitivo para colocar o **10_RTSP_Manager** em produção no nó **Peixe** (Raspberry Pi 3 / Alpine Linux) e acessar as câmeras em tempo real no navegador do PC e smartphone.

---

## ⏱️ Tempo Estimado de Execução: 5 a 10 minutos

---

## 📋 Pré-Requisitos

1. **Credenciais do NVR / Câmeras:**
   * Usuário padrão: `admin`
   * Senha: a senha mestra configurada no NVR (ou deixe em branco se não houver senha definida).
2. **Conectividade:**
   * Acesso SSH ao nó Peixe: `ssh peixe` (ou `ssh peixe-remoto`).
   * Nó Peixe conectado à mesma rede local (`192.168.1.99`).

---

## 🚀 Passo a Passo de Implantação

### Passo 1: Ajustar a Senha no arquivo de configuração

Na sua máquina local (`~/Doc/4/10_RTSP_Manager`):

1. Edite o arquivo [`config/cameras.json`](file:///home/brunoconter/Documentos/4_HOMELAB/10_RTSP_Manager/config/cameras.json) e insira a senha do NVR:
   ```json
   "nvr": {
     "name": "NVR_Principal",
     "mac": "00:12:43:24:4e:c6",
     "ip": "192.168.1.20",
     "user": "admin",
     "password": "SUA_SENHA_AQUI"
   }
   ```
2. Execute o gerador dinâmico para atualizar o `go2rtc.yaml` com as credenciais:
   ```bash
   python3 scripts/dynamic_resolver.py
   ```

---

### Passo 2: Transferir e Instalar o `go2rtc` no Nó Peixe

A partir do seu terminal local:

1. **Copiar o projeto para o nó Peixe:**
   ```bash
   scp -r ~/Doc/4/10_RTSP_Manager peixe:/home/bruno/
   ```

2. **Acessar o nó Peixe e executar o instalador nativo:**
   ```bash
   ssh peixe
   cd /home/bruno/10_RTSP_Manager
   chmod +x scripts/*.sh scripts/*.py
   ./scripts/install_alpine.sh
   ```
   *O instalador baixa o binário oficial ARM64 do go2rtc (~15 MB) e cria o serviço OpenRC `/etc/init.d/go2rtc`.*

3. **Copiar a configuração para `/etc/go2rtc`:**
   ```bash
   cp /home/bruno/10_RTSP_Manager/config/go2rtc.yaml /etc/go2rtc/go2rtc.yaml
   ```

4. **Iniciar o serviço:**
   ```bash
   rc-service go2rtc start
   rc-update add go2rtc default
   ```

5. **Verificar se subiu com baixo consumo:**
   ```bash
   rc-service go2rtc status
   ps aux | grep go2rtc
   free -h
   ```
   *(Consumo esperado: ~25 MB de RAM e < 1% de CPU).*

---

### Passo 3: Ativar o Daemon de Reconciliação (MAC Address) no Crontab

Ainda no nó Peixe, configure a auto-reconciliação para rodar a cada 5 minutos:

```bash
cat << 'CRON' >> /etc/crontabs/root
# Reconciliação contínua de CFTV (resolve IPs via MAC, detecta mudanças e hot-reload)
*/5 * * * * python3 /home/bruno/10_RTSP_Manager/scripts/dynamic_resolver.py > /dev/null 2>&1
CRON
```

---

### Passo 4: Como Ver as Câmeras em Tempo Real 📱💻

#### A. Acesso na Rede Local (Wi-Fi de Casa)
* Abra qualquer navegador moderno (Chrome, Firefox, Safari, Edge) no celular ou notebook.
* Acesse: **`http://192.168.1.99:1984`**
* Clique no botão **`stream`** ao lado do canal desejado (ex: `nvr_canal1`, `camera_frente`).
* O vídeo abrirá instantaneamente em **WebRTC** com latência zero (< 100ms) e sem precisar de nenhum plugin!

#### B. Acesso Remoto Seguro da Rua (via Tailscale)
* Ative o aplicativo **Tailscale** no seu celular ou notebook.
* Acesse: **`http://100.88.42.19:1984`**
* As imagens carregarão com criptografia WireGuard ponta a ponta sem necessidade de abrir portas no roteador da sua casa!

---

### Passo 5: Testar Captura de Foto para o Celular (ntfy)

Para validar a extração de frames e envio instantâneo para o app **ntfy**:

```bash
# Executado do seu terminal ou do nó Peixe:
python3 /home/bruno/10_RTSP_Manager/scripts/capture_snapshot.py \
  --go2rtc 192.168.1.99 \
  --src nvr_canal1 \
  --ntfy \
  --title "Portão Frente 📸"
```
*Seu celular vibrará recebendo a notificação push com a foto em anexo.*

---

## 🛠️ Resolução de Problemas (Troubleshooting)

| Sintoma | Causa Mais Provável | Solução |
| :--- | :--- | :--- |
| Erro `401 Unauthorized` no log do go2rtc | Senha do NVR incorreta ou ausente | Atualize a senha em `config/cameras.json` e rode `scripts/dynamic_resolver.py` |
| Vídeo preto ou carregando infinito | Câmera está desligada ou canal NVR incorreto | Verifique se a câmera responde ao ping e confira o canal no monitor HDMI do NVR |
| Interface web `1984` não abre | Serviço go2rtc parado | Rode `rc-service go2rtc status` ou `rc-service go2rtc restart` |
