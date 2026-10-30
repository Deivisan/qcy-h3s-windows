# Botões físicos do H3S — o que dá e o que não dá

Medido em 29/10/2026 no QCY H3S real, firmware
`30 03 00 01 08`. Tudo aqui é observação de hardware, não leitura de código.

## Resumo

| Pergunta | Resposta curta |
|---|---|
| Dá para **ler** o mapa dos botões? | Sim, mas **não** por `0x2B`. Vem em `GET_ADV_INFO` tipo 2. |
| Dá para **gravar** o mapa? | Sim, por `SET_ADV_INFO` (0xC0) com LTV tipo 2. Testado. |
| O botão ANC é remapeável? | Não aparece no mapa. Nenhuma entrada usa `0xFF`. |
| O `0x2B` (KEYFUN) funciona? | Como leitura, **nunca responde** (timeout). O APK não usa. |
| Nós mexemos nos botões? | Não. `set_button_func` nunca foi chamado por nenhum script. |

## O mapa que o fone devolve

`GET_ADV_INFO` com máscara `1 << 2`:

```
2e 02 | 07 01 01 | 07 02 07 | 07 03 04 | 07 04 00 | 07 05 00
      | 03 01 06 | 03 02 00 | 03 03 00 | 03 04 00 | 03 05 02
      | 05 01 05 | 05 02 00 | 05 03 00 | 05 04 00 | 05 05 03
```

`2e 02` é o LTV (len = 0x2E = 46, tipo = 2). Depois vêm **15 triplas**
`[keyNum, action, function]` — exatamente o formato de
`ADVInfoResponse.KeySettings.toData()` no APK oficial:

```java
public byte[] toData() {
    return new byte[]{ intToByte(keyNum), intToByte(action), intToByte(function) };
}
```

Traduzindo:

| keyNum | action 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 3 | `0x06` | — | — | — | `0x02` |
| 5 | `0x05` | — | — | — | `0x03` |
| 7 | `0x01` | `0x07` | `0x04` | — | — |

`0x00` = sem função. `0x7F` também (o `changeJL2QCY` do APK converte `127 → 0`).
`0xFF` = `KEY_FUNC_ID_SWITCH_ANC_MODE` (constante em `AttrAndFunCode.java`) —
**não aparece em nenhuma entrada**, ou seja o botão ANC não é mapeável por aqui.

## Por que o `0x2B` é uma armadilha

O fork original assumia que remapear botão era `0x2B` (CMDID_BUTTONFUNC).
No hardware:

* leitura `FE 01 2B` → **timeout** (varredura completa: só 13 IDs respondem,
  e `0x2B` não está entre eles);
* escrita `2B 02 key func` é aceita em silêncio, mas o mapa não muda.

O APK não usa `0x2B` para isso. Usa:

```java
// BtRcspOpImpl.configKeySettings()
modifyAdvInfo(2, triplas.toByteArray());   // -> SET_ADV_INFO (0xC0)
// CommandBuilder.buildSetAdvInfoCmd -> packLTVPacket(2, dados)
```

Payload = **a lista inteira**, em LTV: `[len, 0x02, keyNum, action, function, ...]`
com `len = 1 + 3*N`. Para o H3S: 15 entradas → `len = 0x2E`.

**Nunca mande lista parcial.** O SDK trata a lista como a configuração
*completa*; mandar 1 tripla pode apagar as outras 14.

## Como foi validado (sem mudar nada)

Reescrevemos o mapa **idêntico** ao lido e conferimos o read-back:

```
SET_ADV_INFO -> 00          (status 0 = aceito)
depois: [(7,1,1), (7,2,7), (7,3,4), (7,4,0), (7,5,0),
         (3,1,6), (3,2,0), (3,3,0), (3,4,0), (3,5,2),
         (5,1,5), (5,2,0), (5,3,0), (5,4,0), (5,5,3)]
IGUAL: True
```

Se o caminho estivesse errado, o mapa viria diferente — e como o valor enviado
era o mesmo, qualquer diferença seria do nosso lado. Não foi.

## Sobre o botão ANC ter parado de funcionar

**Fatos:**

1. O mapa de botões está intacto e com cara de fábrica (tabela acima).
2. Nenhum script do repo chama `set_button_func` — nem antes nem depois.
3. O caminho antigo (`0x2B`) seria no-op de qualquer forma.
4. O ANC **não** está no mapa: não há entrada com `func = 0xFF`.
5. O botão voltou sozinho depois do reboot, sem nenhum comando de botão.
6. O episódio aconteceu junto com o fone saindo de um restart de firmware
   (`set_ldac(False)`) e com o A2DP preso tentando LDAC (`Error=1`) → HFP.

**Conclusão:** não foi configuração nossa, e não é remapeamento — o botão ANC
não passa pelo RCSP. O estado do fone é que estava atravessado.

**Hipótese (não validada):** o botão ANC cicla entre os modos da lista que o
fone tem em memória (`ADV_TYPE_ANC_MODE_LIST = 10`). Pedimos esse tipo no
`GET_ADV_INFO` e o fone **não devolveu nada** — ele responde só os tipos
0, 1, 2, 4, 5, 6. Se a lista ficou inconsistente com o modo corrente (por
exemplo, modo aplicado por app+Ble enquanto o firmware reiniciava), o ciclo do
botão pode não ter para onde ir e a impressão é "o botão morreu". Não tenho
como provar sem o tipo 10.

## Ferramentas

```python
import asyncio, os, h3s_device as h

dev = h.H3SDevice(os.environ["QCY_H3_BLE_ADDRESS"])
await dev.connect()
await dev.notify_communication_way(way=0)   # handshake obrigatorio no BLE

await dev.get_state()                        # tudo que o firmware responde
await dev.get_key_settings()                 # [(keyNum, action, func), ...]
await dev.set_key_settings(triplas)          # grava a lista COMPLETA
await dev.set_button_func(7, 0xFF, action=1) # troca 1 entrada e regrava o resto
```

No MCP: `get_state` (leitura) e `set_button_func` (escrita, devolve mapa
antes/depois). `get_button_func` existe mas só informa que `0x2B` não responde.
