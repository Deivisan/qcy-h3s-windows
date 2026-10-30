# Controle QCY H3 — Windows

Aplicativo pessoal e independente para Windows para gerenciar fones **QCY H3 / H3S** via Bluetooth Low Energy (BLE). Interface em português e protocolo direto, sem depender do app oficial.

> **Versão 0.1.0-beta:** H3S validado no hardware disponível. A compatibilidade com o H3 padrão ainda está em teste; reporte resultados para ajudar a validar em outros computadores e firmwares.

![Símbolo do Controle QCY H3](assets/qcy-h3-control.svg)

---

## Download — Usuário Final

> Não precisa instalar Python nem nenhuma dependência.

**[Baixar a versão beta 0.1.0](https://github.com/Deivisan/qcy-h3s-windows/releases/tag/v0.1.0-beta)**

### Como usar

1. Ligue o fone e ative o Bluetooth no PC
2. Execute `Controle_QCY_H3_0.1.0-beta.exe`
3. Clique em **Conectar fone** — o fone aparecerá na lista
4. Selecione-o e confirme a conexão
5. Controle ANC, EQ e Game Mode diretamente pelo app

**Requisitos:** Windows 10 ou 11 com adaptador Bluetooth BLE (Bluetooth 4.0+)

---

## Funcionalidades

| Recurso | Descrição |
|---------|-----------|
| **Modos de ruído** | ANC Desligado, Transparência, ANC Baixo, ANC Médio, ANC Alto, Adaptativo |
| **Equalizador 10 bandas** | 55 Hz · 220 Hz · 500 Hz · 1 kHz · 1,8 kHz · 2,8 kHz · 4,5 kHz · 7,5 kHz · 10 kHz · 22 kHz |
| **Presets de EQ** | Custom, Default, Pop, Heavy Bass, Rock, Soft, Classic |
| **Game Mode** | Ativa modo de baixa latência para jogos |
| **Bateria** | Exibe nível atual, atualiza a cada 60 segundos |

### Atalhos e ajuda

| Atalho | Ação |
|---|---|
| `Ctrl+K` | Buscar e conectar fone |
| `Ctrl+G` | Alternar Game Mode |
| `Ctrl+Enter` | Aplicar equalizador |
| `Ctrl+0` | Zerar as bandas do EQ |
| `F1` | Abrir ajuda e compatibilidade |

Os cartões têm entrada animada sutil, os botões indicam seleção/hover e a tela
se adapta a janelas menores por rolagem. Os arquivos vetoriais do símbolo e os
ícones de modo ficam em [`assets/`](assets/).

---

## ⚠️ Comandos destrutivos

Este projeto fala o protocolo RCSP/Jieli direto no fone. Alguns comandos **não
têm volta** e o fone reinicia no meio deles.

| Comando | Efeito |
|---------|--------|
| `set_ldac` (`0x23`) | liga/desliga LDAC — **o fone reinicia** e o A2DP cai |
| `reset_default` (`0x01`) | volta todas as configurações ao padrão |
| `clear_pair` (`0x02`) | apaga os registros de pareamento |
| `factory_reset` (`0x03`) | reset de fábrica |

No servidor MCP essas quatro tools **exigem confirmação explícita**
(`confirm="SET_LDAC"`, `confirm="FACTORY_RESET"`, ...), rodam uma por vez e
entram em quarentena depois de executar.

**Leia antes de usar:** [`docs/COMANDOS-DESTRUTIVOS.md`](docs/COMANDOS-DESTRUTIVOS.md)
— auditoria completa dos ~85 command IDs, com os que são de propósito **não**
expostos (OTA, TESTMODE, SENSOR_TEST, ATPX, PAIRNAME).

---

## O que o fone realmente responde

**Só 13 dos 99 command IDs aceitam leitura** — o resto dá timeout silencioso.
Uma varredura completa está em [`docs/PROTOCOLO-LEITURAS.md`](docs/PROTOCOLO-LEITURAS.md).

Na prática: use `get_state` (MCP) ou `H3SDevice.get_state()`. Ele lê numa
conexão só: bateria, modo ANC, game mode, EQ, LDAC, áudio espacial, sleep mode,
volume do tom, versão e o **mapa dos botões físicos**.

```python
await dev.get_state()
# {'battery_pct': 50, 'anc_index': 7, 'anc_name': 'Adaptativo (AI)',
#  'game_mode': False, 'ldac': False, 'space_sound': False,
#  'sleep_mode': 2, 'tone_volume': 6, 'version_raw': '30 03 00 01 08',
#  'key_settings': [(7, 1, 1), (7, 2, 7), ...]}
```

As tools de leitura sem suporte no firmware (`get_wind_noise`, `get_wear_status`,
`get_focus_mode`, `get_privacy_mode`, ...) agora dizem isso explicitamente em vez
de devolver `null`.

### Botões físicos

O mapa de botões é `[keyNum, action, function]` e vem por `GET_ADV_INFO` tipo 2.
Gravar usa `SET_ADV_INFO` (0xC0) com a **lista inteira** — o `0x2B` do fork
original nunca funcionou. Detalhes e o porquê em
[`docs/BOTOES.md`](docs/BOTOES.md).

---

## Executar a partir do código-fonte

### Pré-requisitos

- Python 3.11 ou superior
- Windows 10/11

### Instalação

```bash
git clone https://github.com/Deivisan/qcy-h3s-windows.git
cd qcy-h3s-windows
pip install PySide6 bleak
python app.py
```

### Gerar o executável

```bash
pip install pyinstaller
python tools/build_icon.py
pyinstaller --noconfirm QCY_H3_Controller.spec
# Resultado: dist/QCY_H3_Controller.exe
```

---

## Estrutura do projeto

```
qcy_h3/
├── app.py            # Ponto de entrada — inicializa Qt e abre a janela
├── main_window.py    # Interface gráfica (PySide6)
├── ble_worker.py     # Worker BLE em thread separada (asyncio + Qt signals)
├── h3_device.py      # Protocolo do dispositivo QCY H3S
└── rcsp.py           # Implementação do protocolo RCSP/JieLi
```

---

## Documentação técnica

### Visão geral

O QCY H3S se comunica via **Bluetooth Low Energy (BLE)** usando o protocolo proprietário **JieLi RCSP** (*Remote Control Service Protocol*), desenvolvido pela JieLi Technology (杰理科技) — fabricante do chip do fone.

A comunicação acontece num serviço GATT customizado:

| Papel | UUID |
|-------|------|
| Serviço | `0000a002-0000-1000-8000-00805f9b34fb` |
| Write (host → fone) | `00000001-0000-1000-8000-00805f9b34fb` |
| Notify (fone → host) | `00000002-0000-1000-8000-00805f9b34fb` |

---

### Chip e firmware

O fone usa um **JieLi JL7018F6** (32-bit dual-core DSP, BT 6.0 + BR/EDR + BLE,
LDAC/LHDC/AAC/SBC). O estudo completo de viabilidade de firmware — fluxo OTA
RCSP, quais checagens o fone faz, o container `.UFW` e por que não existe
assinatura criptográfica — está em
[`qcy-toolkit/docs/FIRMWARE-JL7018.md`](https://github.com/Deivisan/qcy-toolkit/blob/main/docs/FIRMWARE-JL7018.md).

Resumo: **este projeto não implementa OTA.** Não por falta de protocolo (o
formato está mapeado), mas porque um flash errado pode brickar o fone e não há
firmware alternativo para gravar.

### Protocolo RCSP — formato de pacote

Todos os pacotes seguem a estrutura:

```
[FE DC BA] [flag:1] [opCode:1] [paramLen:2 BE] [sn:1] [params:N] [EF]
```

| Campo | Tamanho | Descrição |
|-------|---------|-----------|
| Header | 3 bytes | `FE DC BA` fixo |
| flag | 1 byte | bit7=tipo (1=comando, 0=resposta), bit6=esperaResposta |
| opCode | 1 byte | Operação desejada |
| paramLen | 2 bytes | Tamanho do corpo (big-endian), inclui o `sn` |
| sn | 1 byte | Número de sequência — a resposta devolve o mesmo `sn` |
| params | N bytes | Parâmetros da operação |
| Footer | 1 byte | `EF` fixo |

**Exemplo — GetTargetInfo (opCode=3, sem parâmetros):**
```
FE DC BA  C0  03  00 01  01  EF
│         │   │   │       │
│         │   │   │       └─ sn=1
│         │   │   └──────── paramLen=1 (só o sn)
│         │   └──────────── opCode=3 (GET_TARGET_INFO)
│         └────────────────  flag=0xC0 (comando + espera resposta)
└──────────────────────────  header
```

---

### OpCodes relevantes

| Constante | Valor | Uso |
|-----------|-------|-----|
| `GET_TARGET_INFO` | 3 | Info do dispositivo |
| `NOTIFY_COMMUNICATION_WAY` | 11 | Handshake inicial (BLE=0) |
| `GET_SYS_INFO` | 7 | Informações do sistema |
| `SET_ADV_INFO` | 192 (0xC0) | Configura parâmetros de anúncio (game mode) |
| `GET_ADV_INFO` | 193 (0xC1) | Lê parâmetros (bateria, game mode) |
| `CUSTOM` | 255 (0xFF) | Sub-protocolo QCY (ANC, EQ) |

---

### Sub-protocolo Custom (opCode 0xFF)

Todos os comandos de ANC e EQ usam o opCode `CUSTOM` com parâmetros que seguem o padrão:

- **GET:** `FE 01 [cmd]` — solicita leitura do recurso `cmd`
- **SET:** `[cmd] [len] [dados...]` — grava o recurso

---

### Modos de ruído (ANC)

Parâmetros do comando Custom, sub-comando `0x17`:

```
params = [0x17, 0x03, sub, group, level]
```

| Modo | sub | group | level | Label no app |
|------|-----|-------|-------|--------------|
| ANC Desligado | `0x02` | `0x00` | `0x00` | ANC Desligado |
| Transparência | `0x03` | `0x01` | `0x04` | Transparência |
| ANC Baixo | `0x01` | `0x01` | `0x00` | ANC Baixo |
| ANC Médio | `0x01` | `0x01` | `0x01` | ANC Médio |
| ANC Alto | `0x01` | `0x01` | `0x02` | ANC Alto |
| Adaptativo | `0x01` | `0x05` | `0x00` | Adaptativo |

Para **ler** o modo atual:
```
GET params = [0xFE, 0x01, 0x17]
```

---

### Equalizador (10 bandas)

#### Leitura

```
GET params = [0xFE, 0x01, 0x22]
```

A resposta retorna uma lista de entradas de 7 bytes cada:

```
[freq:2 LE] [delta_db:2 LE signed] [ref_gain:2 LE] [Q:1]
```

Frequências suportadas (little-endian):

| Label | Valor (hex) |
|-------|-------------|
| 55 Hz | `0x0037` |
| 220 Hz | `0x00DC` |
| 500 Hz | `0x01F4` |
| 1 kHz | `0x03E8` |
| 1,8 kHz | `0x0708` |
| 2,8 kHz | `0x0AF0` |
| 4,5 kHz | `0x1194` |
| 7,5 kHz | `0x1D4C` |
| 10 kHz | `0x2710` |
| 22 kHz | `0x55F0` |

O `delta_db` está em **centésimos de dB** (ex.: `+600` = `+6,00 dB`).

#### Gravação

```
SET params = [0x22] [data_len] [preset_id] [0x70] [0xFE] [10 × 7 bytes de banda]
```

`data_len` = 3 (cabeçalho) + 70 (bandas) = `0x49`

**preset_id:**

| ID | Preset |
|----|--------|
| `0x00` | Custom (definido pelo usuário) |
| `0x01` | Default |
| `0x02` | Pop |
| `0x03` | Heavy Bass |
| `0x04` | Rock |
| `0x05` | Soft |
| `0x06` | Classic |

---

### Game Mode

Usa o opCode `SET_ADV_INFO` (0xC0) com parâmetros no formato TLV:

```
params = [0x02, 0x05, value]
         │      │     └─ 0x02 = ativar, 0x01 = desativar
         │      └──────── ADV type 5 = WORK_MODE
         └─────────────── length = 2
```

Para ler o estado atual, usa `GET_ADV_INFO` (0xC1) com máscara `1 << 5`.

---

### Bateria

Usa `GET_ADV_INFO` (0xC1) com máscara `1 << 0` (ADV type 0 = BATTERY_QUANTITY).

A resposta vem em formato TLV: `[len][type][value...]`  
`value[0]` = percentual da bateria (0–100).

---

### Handshake de conexão

Após conectar via BLE e registrar as notificações, é obrigatório enviar:

```python
Packet(op_code=OpCode.NOTIFY_COMMUNICATION_WAY, params=bytes([0x00, 0x00]))
# way=0 (BLE), reconnect=0
```

Sem esse handshake o dispositivo não responde a comandos subsequentes.

---

### Arquitetura da aplicação

```
Qt Main Thread                    BLE Thread (daemon)
──────────────────────            ──────────────────────────
MainWindow                        BleWorker._run_loop()
  │                                 asyncio event loop
  ├─ clica Escanear ──────────────► _do_scan()
  │                                   BleakScanner.discover()
  │◄─ scan_result(list) ────────────── emit()
  │
  ├─ seleciona device ────────────► _do_connect(addr)
  │                                   H3Device.connect()
  │                                   notify_communication_way()
  │                                   _do_refresh()
  │◄─ connected(addr) ──────────────── emit()
  │◄─ battery_updated(pct) ─────────── emit()
  │◄─ mode_updated(idx) ────────────── emit()
  │◄─ eq_updated(offsets) ──────────── emit()
  │
  ├─ clica modo ANC ──────────────► _do_set_mode(bytes)
  ├─ clica Apply EQ ──────────────► _do_set_eq(offsets, preset_id)
  └─ clica Game Mode ─────────────► _do_set_game_mode(enabled)
```

Os sinais Qt cruzam a barreira de threads com segurança via **queued connection** automática do PySide6.

---

## Licença

MIT License — livre para usar, modificar e distribuir.
