# Compatibilidade: QCY H3 e QCY H3S

## Escopo do aplicativo

O Controle QCY H3 foi desenvolvido para a família **QCY H3**, incluindo o **H3
padrão** e o **H3S**. O aplicativo usa Bluetooth Low Energy e comandos RCSP/JieLi
compartilhados pela família. A presença de suporte para um recurso pode mudar
com a revisão de hardware e o firmware instalado.

## Matriz de validação

| Modelo | Situação | Observação |
|---|---|---|
| QCY H3S | Testado em hardware | Conexão BLE, modos de ruído, Game Mode, bateria e alteração/read-back do EQ foram verificados na unidade disponível. |
| QCY H3 padrão | Modelo-alvo; validação externa pendente | O projeto foi preparado para H3 e H3S, mas ainda não houve teste em uma unidade H3 padrão. Compatibilidade de cada recurso depende da revisão/firmware. |

Assim, o aplicativo **é destinado a ambos os modelos**, mas a evidência de
hardware que acompanha esta versão é do H3S. Se usar o H3 padrão, pedimos que
informe o firmware e quais controles funcionaram; não trate o estado selecionado
na interface sozinho como confirmação do fone.

## Recursos e evidência

| Recurso | H3S | H3 padrão |
|---|---|---|
| Conexão BLE/handshake RCSP | Observado e testado | A validar em dispositivo real |
| Modos de ruído / adaptativo | Comandos usados; confirmação física varia | A validar |
| Game Mode | Estado lido e comando verificado | A validar |
| Equalizador 10 bandas | SET seguido de GET; alteração temporária e restauração confirmadas | A validar |
| Bateria | Leitura confirmada | A validar |

Funções sem read-back confiável ou sem evidência no hardware não estão na UI.
Isso inclui áudio espacial, redução de vento, detecção de uso, tom de toque e os
botões Música/Filme/Jogo. Não confunda o Game Mode dedicado (baixa latência) com
um modo de cena de áudio.

## Como contribuir com a validação do H3

Use a lista em [Testes da beta](TESTES-BETA.md). Não envie endereço Bluetooth,
serial ou dados pessoais publicamente. Informe apenas o modelo, revisão/firmware
se conhecido, Windows, adaptador Bluetooth e o resultado funcional.
