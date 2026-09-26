# 🛑 Rastreador de Issues & Pendências: 10_RTSP_Manager

Este documento centraliza as issues técnicas, anomalias de hardware e investigações em andamento no parque de CFTV do cluster Homelab.

---

## 📌 Issue #001: Falha de Sinal de Vídeo no Canal 01 (NVR Xiongmai)

* **Status:** 🟢 **RESOLVIDA (2026-09-26)**
* **Componente:** Câmera Varanda (`192.168.1.16:554` - Canal 1) / go2rtc Peixe
* **Data de Abertura:** 2026-09-15
* **Data de Resolução:** 2026-09-26
* **Solução:** Câmera física Xiongmai Dual-Lens (Varanda) localizada no IP `192.168.1.16` (MAC `d4:a3:eb:89:bd:f4`). Stream direto RTSP integrado com sucesso ao `go2rtc` nativo com perfil H.264 para navegadores.
* **Severidade:** Média (Todos os 6 canais [01, 02, 03, 04, 05, 06] 100% operacionais)

---

### 1. Descrição do Problema
O Canal 1 do NVR responde a negociações RTSP (porta `554`), porém não envia fluxo de dados de vídeo (`0x0`, `unspecified size`). Ferramentas como `ffprobe` e `ffmpeg` entram em timeout de conexão esperando dados RTP ou retornam `Output file does not contain any stream`.

Na interface do NVR, o canal 1 apresenta sintoma típico de **"Perda de Vídeo" (Video Loss)**.

---

### 2. Evidências Técnicas Coletadas

| Teste | Comando Executado | Resultado |
| :--- | :--- | :--- |
| **RTSP Stream 0 (Main)** | `rtsp://brunoconter:blurbang@192.168.1.20:554/...&channel=1&stream=0.sdp` | Timeout / Stream vazio (0 bps) |
| **RTSP Stream 1 (Sub)** | `rtsp://brunoconter:blurbang@192.168.1.20:554/...&channel=1&stream=1.sdp` | Timeout / Sem dados de quadro |
| **Varredura de Portas** | `nmap` / script Python na LAN | Portas 554/34567 ativas em 5 nós (`.4`, `.5`, `.6`, `.10/.11`, `.31`) |

---

### 3. Hipóteses Diagnósticas

1. **Falha de Alimentação Elétrica (Mais provável):**
   * A fonte de alimentação 12V DC da câmera do Canal 1 pode ter queimado ou sido desconectada da tomada.
2. **Falha de Conectividade Física (Cabo / Conector RJ45):**
   * Cabo de rede rompido, conector oxidado por intempéries ou porta do switch/injetor PoE sem link de dados.
3. **Desconfiguração de IP da Câmera (DHCP):**
   * Se a câmera estiver ligada mas perdeu o IP estático registrado no NVR, o NVR continua tentando buscar o feed em um endereço que não existe mais.
4. **Defeito no Sensor/Placa da Câmera:**
   * Câmera queimada por surto elétrico ou infiltração.

---

### 4. Checklist de Ação Física (Investigação de Campo)

- [ ] **Identificação Física:** Localizar fisicamente qual câmera da casa corresponde ao Canal 1 (ex.: Frente, Garagem, Fundos, Corredor).
- [ ] **Inspeção Visual de LEDs:**
  - Cobrir a lente ou o sensor de luminosidade com a mão e escutar se há clique do filtro mecânico IR-CUT.
  - Verificar se os LEDs infravermelhos (anel ao redor da lente) acendem em vermelho fraco no escuro.
- [ ] **Inspeção de Cabeamento:**
  - Conferir se o cabo de rede está firmemente plugado no switch / roteador / injetor PoE.
  - Verificar se os LEDs de link (verde/laranja) da porta correspondente no switch estão acesos e piscando.
- [ ] **Conferência no Monitor do NVR (HDMI):**
  - Acessar o menu do NVR: `Menu Principal > Configurar > Câmeras > Gestão de Canais`.
  - Checar qual endereço IP está atribuído ao Canal 1 e se o status consta como `Conectado`, `Desconectado`, ou `Senha Incorreta`.
- [ ] **Teste de Bancada (se necessário):**
  - Descer a câmera e conectá-la diretamente a um patch cord curto no switch para testar fonte e rede.
