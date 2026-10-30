# QCY H3S Controller — Windows Edition

App desktop para Windows que permite controlar o fone de ouvido **QCY H3S** via Bluetooth Low Energy (BLE), sem depender do aplicativo oficial da QCY.

---

## Download — Usuário Final

> Não precisa instalar Python nem nenhuma dependência.

**[⬇ Baixar QCY_H3_Controller.exe](https://github.com/GMarzochi/QCY_H3_WIndowsEdition/releases/latest/download/QCY_H3_Controller.exe)**

### Como usar

1. Ligue o fone e ative o Bluetooth no PC
2. Execute o `QCY_H3_Controller.exe`
3. Clique em **Escanear** — o fone aparecerá na lista
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

---

## Executar a partir do código-fonte

### Pré-requisitos

- Python 3.11 ou superior
- Windows 10/11

### Instalação

```bash
git clone https://github.com/GMarzochi/QCY_H3_WIndowsEdition.git
cd QCY_H3_WIndowsEdition
pip install PySide6 bleak
python app.py
```

### Gerar o executável

```bash
pip install pyinstaller
pyinstaller --windowed --onefile --name "QCY_H3_Controller" \
    --hidden-import "bleak.backends.winrt" \
    --collect-all "bleak" app.py
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
