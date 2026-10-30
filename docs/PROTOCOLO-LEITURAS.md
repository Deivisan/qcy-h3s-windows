# O que o firmware responde (e o que não)

Medido no H3S real em 29/10/2026, firmware `30 03 00 01 08`. Varredura dos
command IDs `0x01`–`0x63` mais alguns altos, um por um, com timeout de 1.2 s.

**Resultado: 13 de 99 IDs respondem leitura.** O resto dá timeout silencioso.

## Os 13 que respondem (`FE 01 <id>`)

| Cmd | Nome no APK | Resposta medida | Observação |
|-----|-------------|-----------------|------------|
| `0x10` | `CMDID_SLEEPMODE` | `10 01 02` | valor 2 = ? (não validado) |
| `0x14` | `CMDID_POWERMANAGER` | `14 04 ff ff 00 00` | `ff ff` nos dois lados |
| `0x17` | `CMDID_ANCSETTING` | `17 03 02 00 00` | modo ANC (ver nota abaixo) |
| `0x19` | `CMDID_VOICENAME` | `19 04 4a 4c 30 30` | `"JL00"` |
| `0x1D` | `CMDID_TONEVOLUME` | `1d 02 06 08` | volume do tom + máximo |
| `0x1F` | `CMDID_STANDBY` | `1f 02 05 00` | |
| `0x22` | `CMDID_MULTIEQ2` | 74 bytes | EQ 10 bandas |
| `0x23` | `CMDID_LDAC` | `23 01 00` | off |
| `0x24` | `CMDID_1T2` | `24 01 00` | |
| `0x2D` | `CMDID_SPACE_SOUND` | `2d 01 00` | áudio espacial |
| `0x2E` | `CMDID_MUSIC_MODE` | `2e 01 01` | |
| `0x2F` | `CMDID_BATTERY` | `2f 03 00 32 00` | `0x32` = 50% |
| `0x30` | `CMDID_VERSION` | `30 03 00 01 08` | 1.8 |

## Os que **não** respondem (e as tools que dependiam deles)

| Tool do MCP | Cmd | Situação |
|---|---|---|
| `get_wind_noise` | `0x2A` | timeout |
| `get_touch_tone` | `0x31` | timeout |
| `get_led_mode` / `get_led_switch` / `get_led_effect` | `0x12` / `0x35` / `0x36` | timeout |
| `get_focus_mode` | `0x39` | timeout |
| `get_adapt_volume` | `0x40` | timeout |
| `get_inear_sensitivity` | `0x48` | timeout |
| `get_env_adaptation` | `0x32` | timeout |
| `get_ai_anc` | `0x54` | timeout |
| `get_hearing_safety` | `0x58` | timeout |
| `get_spatial_audio` | `0x5B` | timeout |
| `get_privacy_mode` | `0x5F` | timeout |
| `get_wear_status` | `0x62` | timeout |
| `get_button_func` | `0x2B` | timeout (use `get_state`) |
| `get_device_info` | `0xF7` | timeout |

Essas tools agora **dizem** que não são suportadas em vez de devolverem `None`.
O SET delas continua existindo (fire-and-forget), mas não há como confirmar o
estado — trate como "pode não ter feito nada".

## Canal alternativo: `GET_ADV_INFO` (0xC1)

Melhor caminho para estado, porque é uma requisição só e devolve TLV:

```
máscara 0x0FFF -> 2e 02 (...) 08 01 51 43 59 20 48 33 53 04 00 32 00 00 ...
```

Tipos que o H3S devolve: **0** (bateria), **1** (nome), **2** (mapa de botões),
**4** (canal do mic), **5** (work mode = game mode), **6** (product message).
Pedimos 3 (LED), 7–12 (tempo conectado, in-ear, idioma, sleep, lista ANC,
balanço) e **nada voltou**.

`get_state()` usa esse canal + os IDs acima e devolve tudo numa conexão.

## Dois bugs que a varredura revelou

### `set_tone_volume` nunca funcionou

Código antigo: `[0x1D, 0x01, volume]` — payload de 1 byte.
Firmware espera: `[0x1D, 0x02, volume, 0x00]` — 2 bytes, faixa **0..8**.

Prova: `set_tone_volume(10)` → leitura continua `6`. Com o payload certo,
`0x00..0x08` são aceitos e ecoados:

```
set [0x04 0x00] -> leu 1d 02 04 08
set [0x08 0x00] -> leu 1d 02 08 08
```

O 4º byte da leitura (`0x08`) é o máximo; no SET pode ir `0x00`.

### `ANC_SETTING` (0x17) **ecoa qualquer coisa**

`17 03 01 01 FF`, `sub 0x07`, `grupo 0x09` — tudo voltou igual ao enviado.
Ou seja: ler `0x17` **não é prova de que o fone aceitou o modo**. Foi assim que
um teste anterior "descobriu" níveis 5 e 6 que não existem: era eco do lixo.
A prova real é auditiva, ou comparar o modo com o que a GUI mostra.
`ANCMode.from_params()` agora devolve `None` para payload fora da tabela.

## Verificação de transporte do EQ (30/10/2026)

O `SET` de EQ usa o custom command `0x22` e um frame RCSP de cerca de 84 bytes.
Nesta máquina, Bleak/WinRT negociou ATT MTU 247 e a característica RCSP reportou
`max_write_without_response_size=244`, portanto o frame cabe em uma escrita. O
código ainda fragmenta pelo limite reportado para não depender disso em outros
adaptadores/MTUs.

Teste não destrutivo no H3S: ler EQ original (10 bandas todas em `0`), mudar
temporariamente a primeira banda para `+100` (centésimos de dB), receber ACK com
status `0`, ler de volta exatamente `[100, 0, ...]` e restaurar `[0, ...]`,
também confirmado por read-back. Isso valida formato, transporte e aplicação do
EQ neste firmware; o problema observado era a escrita do frame maior que o
limite ATT em conexões sem MTU suficiente, sem fragmentação.

Os botões inferiores Música/Filme/Jogo foram retirados: embora `0x2E` responda
leitura, os SETs desses valores não foram validados de forma confiável no H3S.
O Game Mode superior (`SET_ADV_INFO` work mode) permanece separado e validado.
