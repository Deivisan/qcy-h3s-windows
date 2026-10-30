# Comandos destrutivos e auditoria de risco — QCY H3S (RCSP/Jieli)

> Documento criado em **29/10/2026** depois de um incidente real. Ele existe
> porque o `mcp_server.py` foi escrito sem auditoria: 48 tools expostas em cima
> de ~85 command IDs, sem classificação de risco, sem confirmação e sem
> serialização. Um agente podia mandar `set_ldac` + `set_anc_mode` + `set_eq`
> em sequência e derrubar o fone no meio.

Fonte de verdade dos IDs: APK oficial decompilado, em
`qcy-toolkit/apk/qcy-audio-decompiled/sources/com/qcymall/qcydevicelibrary/constant/ConstantCMDID.java`.

---

## Regras (não são sugestões)

1. **Comando destrutivo nunca anda em lote.** Um por vez, e nada em cima até a
   quarentena acabar. O servidor MCP já força isso com `_lock` + `COOLDOWN`.
2. **Comando destrutivo exige confirmação explícita** no campo `confirm`, com o
   nome da tool em maiúsculas (`confirm="SET_LDAC"`). Sem isso a chamada é
   recusada antes de tocar no BLE.
3. **Depois de destrutivo, reconecte e releia o estado.** O fone reinicia e o
   que estava em RAM some.
4. **Nunca confie no "OK" do comando.** O H3S responde `status=0` para vários
   comandos que ele simplesmente ignora. Depois de escrever, faça o `get_`
   correspondente e compare.
5. **Não empilhe GETs durante um destrutivo.** Se o fone está reiniciando, o
   `BleakScanner` volta vazio e você vai concluir "o fone morreu".
6. **Uma conexão BLE por vez.** O H3S aceita **um único** cliente BLE. Enquanto
   alguém segura o link, todo o resto vê "0 dispositivos" no scan — inclusive
   um segundo processo seu. Ver a seção abaixo.

---

## Tiers de risco

| Tier | Nome | Efeito |
|------|------|--------|
| **R0** | leitura | `0xFE 0x01 <id>` — GET puro, não muda nada |
| **R1** | escrita reversível | muda ajuste persistido, link continua |
| **R2** | efeito externo | mexe no celular pareado ou emite som alto |
| **R3** | **destrutivo** | reinicia o fone, apaga pareamento ou apaga a config |

---

## R3 — destrutivos

| Cmd | Nome no APK | Tool MCP | O que faz de verdade | Evidência |
|-----|-------------|----------|----------------------|-----------|
| `0x23` | `CMDID_LDAC` (35) | `set_ldac` | Liga/desliga LDAC. **O fone reinicia.** Como efeito colateral, o link A2DP cai e no Windows o driver Alternative A2DP fica com `Current.Codec=0, Error=1`. | Medido em 29/10/2026: `set_ldac(False)` → fone reinicia → A2DP `UNPLUGGED` → só HFP ativo → microfone do fone aberto como captura padrão. |
| `0x01` | `CMDID_RESET_DEFAULT` (1) | `reset_default` | Volta todas as configurações ao padrão. Persiste. | APK |
| `0x02` | `CMDID_CLEAR_PAIR` (2) | `clear_pair` | Apaga os registros de pareamento do fone. **Você perde o vínculo com todos os dispositivos.** | APK |
| `0x03` | `CMDID_FACTORY_RESET` (3) | `factory_reset` | Reset de fábrica. É o que a própria QCY usa para "esqueci o fone". | APK |
| — | OTA / firmware | **não exposto, de propósito** | Atualização de firmware. Um payload errado aqui brick. | decisão de projeto |

> **"chpoint"**: mapeado aqui como a família `clear_pair` / `factory_reset`
> (comandos que apagam estado e não têm volta). Se você quis dizer outro
> comando, corrija esta tabela.

### Quarentena aplicada (`mcp_server.COOLDOWN`)

```python
"set_ldac":       12.0,   # fone reinicia, volta em ~8-12 s
"factory_reset":  15.0,
"clear_pair":     12.0,
"reset_default":   8.0,
```

Depois do comando o servidor **desconecta de propósito** e bloqueia a próxima
chamada por esse tempo. O objetivo é não gerar tempestade de reconexão.

---

## R2 — efeito externo / som alto

| Cmd | Tool MCP | Risco específico |
|-----|----------|------------------|
| `0x04` | `music_control` | Play/pause/next/prev **no celular pareado**. Mexe no que a pessoa está ouvindo. |
| `0x1E` | `take_photo` | Dispara o obturador da câmera do celular pareado. Efeito fora do fone. |
| `0x4B` | `find_earphones` | Bipe de localização. Toca **no volume atual** — num over-ear pode ser doloroso. |
| `0x3D` | `play_tone` | Tom de teste. Mesmo problema. |

---

## R1 — escrita reversível

| Cmd | Tool MCP | Observação |
|-----|----------|------------|
| `0x17` | `set_anc_mode` | Usa `ANCMode.ALL` |
| `0x74`(0x4A)/ADV | `set_game_mode` | via `SET_ADV_INFO` |
| `0x22` | `set_eq` | 10 bandas, agora validado |
| `0x08` | `set_volume` | agora clamp 0-100 |
| `0x16` | `set_balance` | agora clamp 0-255 |
| `0x1D` | `set_touch_tone_volume` | agora clamp 0-100. **Se zerar, os avisos de voz somem** ("não fala nem que está conectado"). |
| `0x48` | `set_in_ear_sensitivity` | clamp 0-255 |
| `0x5B` | `set_spatial_audio` | leitura de volta não decodifica |
| `0x2D` | `set_spatial_sound` | demora alguns segundos pra refletir |
| `0x2A` | `set_wind_noise` | |
| `0x2C` | `set_wear_config` | |
| `0x31` | `set_touch_tone` | |
| `0x54` | `set_ai_anc` | |
| `0x10` | `set_sleep_mode` | |
| `0x39` | `set_focus_mode` | |
| `0x5F` | `set_privacy_mode` | |
| `0x40` | `set_adapt_volume` | |
| `0x32` | `set_env_adaptation` | |
| `0x12` | `set_led_mode` | |
| `0x35` | `set_led_switch` | |
| `0x05` | `set_light` | |
| `0x2B` | `set_button_func` | remapeia toque físico — mexer aqui pode te deixar sem controle no fone |
| `0x3E` | `sync_time` | **NÃO TESTADO.** Ver bug abaixo |

---

## IDs perigosos que **não** estão expostos (e devem continuar assim)

| Cmd | Nome no APK | Por quê |
|-----|-------------|---------|
| `0x0D` | `CMDID_TESTMODE` | modo de teste de fábrica |
| `0x52` | `CMDID_SENSOR_TEST` | teste de sensor |
| `0x45` | `CMDID_CUSTOM_EQ_TEST` | EQ de teste |
| `0x51` | `CMDID_SENSOR_CONFIG` | calibração de sensor |
| `0x1B` | `CMDID_ATPX` | troca de codec aptX |
| `0x3F` | `CMDID_ALARM` | alarme persistido |
| `0x18` | `CMDID_PAIRNAME` | renomeia o fone — quebra reconexão automática |
| `0x1A` | `CMDID_VOICE_LANGUAGE` | troca o idioma dos avisos |
| — | OTA (`JL_OTALib`) | risco de brick |

---

## Bugs reais encontrados nesta auditoria (29/10/2026)

### 1. Constantes de ANC com nome trocado — armadilha real

O byte que decide o modo é `params[2]`:

```
0x17 0x03 <sub> <grupo> <nível>
```

e `ANCMode.from_params()` numera: `sub=0x02 → 0 (ANC desligado)`,
`sub=0x03 → 1 (transparência)`, `sub=0x01 → 2..6`, `grupo=0x05 → 7 (adaptativo)`.

O problema: as duas constantes estavam nomeadas ao contrário do payload.

| Constante (nome antigo) | Payload | O que realmente fazia |
|---|---|---|
| `TRANSPARENCY` | `17 03 02 00 00` | **ANC desligado** |
| `NORMAL` | `17 03 03 01 04` | **Transparência** |

A ordem de `ALL` estava compensando isso, então **o app funcionava**. Mas o nome
mentia, e qualquer refactor que "arrumasse" a ordem trocava os dois modos de
verdade — foi o que aconteceu comigo durante esta auditoria: reordenei `ALL`
achando que havia bug e passei a mandar transparência no índice 0.

Resolvido renomeando as constantes (`ANC_OFF`, `TRANSPARENCY`, com alias
`NORMAL = TRANSPARENCY`) e **mantendo a ordem de bytes**. Verificação:

```
  0 ANC desligado      17 03 02 00 00  -> from_params=0   OK
  1 Transparência      17 03 03 01 04  -> from_params=1   OK
  2 ANC baixo          17 03 01 01 00  -> from_params=2   OK
  ...
  7 Adaptativo (AI)    17 03 01 05 00  -> from_params=7   OK
```

Todos os 8 índices batem com `MODE_LABELS` da GUI.

### 2. `sync_time` mandava `month + 1`

`bytes([... month + 1 ...])` — em dezembro gerava mês **13**. Agora usa mês
1-based com clamp. **NÃO TESTADO no hardware.**

### 3. Truncamento silencioso de valores

`set_volume(300, 300)` virava `44` porque o valor passava por `& 0xFF`.
`set_tone_volume(200)` idem. Agora existe `_clamp()` e valores fora da faixa
são limitados (ou viram `TypeError` se nem forem `int`).

### 4. Tools duplicadas no MCP

`set_ldac`, `set_sleep_mode` e `set_touch_tone` estavam registradas **duas
vezes** cada. O registro agora é um `dict`, então duplicata é impossível.

### 5. Nenhuma serialização

`get_device()` não tinha lock: duas chamadas concorrentes criavam dois
`BleakClient`, corrompiam o contador `sn` do RCSP e deixavam processo pendurado
segurando o BLE (foi o que gerou os 4 `python.exe mcp_server.py` órfãos).
Agora tudo passa por um `asyncio.Lock` global.

### 6. `set_eq` sem validação

Lista com 9 itens estourava `IndexError` no meio da montagem do pacote; valores
> 1200 estouravam o campo de 2 bytes. Agora exige exatamente 10 itens e faz
clamp em ±1200.

---

## Só existe uma conexão BLE — e ela derruba o scan

Medido em 29/10/2026, com o mesmo código, minutos de diferença:

| Situação | `BleakScanner.discover()` | `BleakClient(addr).connect()` |
|---|---|---|
| Nenhum outro processo com o fone | 0 dispositivos (scan já quebrado no BARROT) | **OK**, 2 services |
| `mcp_server.py` segurando o link | 0 dispositivos | **falha** |

Duas conclusões separadas, as duas importam:

1. **Este dongle não entrega anúncios BLE.** O `BluetoothLEAdvertisementWatcher`
   fica em `status = Created (0)` e nunca recebe nada, mesmo com
   `IsLowEnergySupported = True` e `IsCentralRoleSupported = True`. Combina com
   o aviso do próprio Windows no event log:

   > BTHUSB: O adaptador local não tem o requisito de buffer mínimo para dar
   > suporte à filtragem de hardware de anúncios de Bluetooth de Baixa Energia.

   **Consequência prática:** nunca dependa de scan. Conecte direto no endereço
   fixo. É por isso que `mcp_server._connect()` tenta o endereço fixo **antes**
   do scan.

2. **O H3S aceita um cliente BLE por vez.** Processo pendurado segurando a
   conexão = todo o resto falha, e o erro aparece como "não encontrado", que é
   enganoso. Antes de concluir "fone morreu", mate os `python.exe` órfãos:

   ```powershell
   Get-Process python | Where-Object { $_.StartTime -lt (Get-Date).AddMinutes(-5) } | Stop-Process -Force
   ```

Processo órfão já causou isso duas vezes neste projeto (4 `mcp_server.py`
duplicados numa, 1 nesta).

---

## Contexto Windows: por que o A2DP caiu e o mic abriu

Não foi comando RCSP. Foi o driver **Alternative A2DP Driver** (1.8.3.1) preso
tentando LDAC num fone que já estava sem LDAC:

```
Capability.Codec = 3    (SBC + AAC — o fone só anuncia isso agora)
Current.Codec    = 0    (nada negociado)
Current.Error    = 1    (falhou ao abrir o stream)
Current.Opened   = 0
```

Sem A2DP, o Windows cai no HFP: os endpoints `Headset (QCY H3S Hands-Free)`
ficam `Active` em **render e capture** — é isso que "abre o microfone".

O fabricante do driver confirma o problema do adaptador (FAQ oficial):

> BARROT Bluetooth 5.4 and 6.0 Adapter Chips (sold as UGREEN Bluetooth 5.4 and
> 6.0 Adapters) Problems — ... the bitrates are limited to less than 200 kbps for
> both CODECs ... If you are using these adapters and are experiencing problems,
> try using a different one.

Nosso dongle é exatamente `VID_33FA&PID_0012&REV_8891` (CM748 75073), listado
na tabela deles.

Achados correlatos:
- `BluetoothUserService_<sid>` fica `Stopped` e **o A2DP não sobe** sem ele.
- O driver tem um bug histórico (corrigido no 1.7.0) de "A2DP fica
  inutilizável se o rádio for desligado e ligado rápido" — que é exatamente o
  que fizemos com `Radio.SetStateAsync(OFF/ON)`.
- Apagar `Parameters\Devices\Current\<mac>` e `Capability\<mac>` e reiniciar o
  serviço regenera tudo — e ele falha igual. **Não é corrupção de registro.**

### Se o A2DP continuar com `Error=1`

A saída é remover o driver e voltar ao A2DP nativo do Windows (AAC/SBC):

```powershell
pnputil /delete-driver oem2.inf /uninstall
```

Custo: perde LDAC. Benefício: A2DP estável e microfone do fone sem ficar aberto.
