# Perguntas frequentes e solução de problemas

## O aplicativo funciona com o QCY H3 normal e com o H3S?

O aplicativo foi feito para os dois. O H3S foi validado em hardware; a
compatibilidade do H3 padrão ainda precisa de teste em uma unidade física. Veja
a [matriz de compatibilidade](COMPATIBILIDADE.md) e ajude com um [relato de
teste](TESTES-BETA.md).

## O fone não aparece na busca

1. Ligue o headset, aproxime-o do PC e confirme que o Bluetooth está ligado.
2. Feche temporariamente o aplicativo oficial da QCY e outros controladores BLE;
   alguns mantêm a conexão de controle ocupada.
3. Tente buscar novamente. Se o Windows já conhece o dispositivo, mas não o
   anuncia, use o endereço BLE manual, caso o tenha identificado antes.
4. Endereço clássico exibido em Configurações Bluetooth e endereço BLE podem
   ser diferentes. Não copie um MAC clássico presumindo que é o GATT do fone.

## A busca encontra o fone, mas conectar expira

Desconecte o app oficial/outro cliente, feche e reabra o Controle QCY H3 e tente
novamente. Se continuar falhando, desligue e ligue o Bluetooth do PC. Evite
remover o pareamento do Windows como primeira tentativa.

## Cliquei num modo, mas o fone não confirmou

O status do aplicativo distingue o envio do comando da leitura confirmada. Em
alguns firmwares, a resposta ANC pode apenas ecoar os bytes enviados. Confirme
também pelo comportamento de áudio e pelo anúncio de voz do próprio fone; a fala
é gerada pelo firmware e não é garantida pelo aplicativo.

## O EQ não aplicou ou voltou ao valor anterior

O app lê o EQ depois do SET. Se o read-back não corresponder, os controles
mostram o que o fone devolveu em vez de manter uma confirmação falsa. Isso pode
indicar limite de firmware, conexão BLE concorrente ou diferença de protocolo.
Anote o modelo/revisão e os passos, mas não publique seu endereço MAC.

## A janela ou os textos aparecem cortados

Maximize a janela ou use a rolagem vertical. O layout suporta janelas menores,
mas a beta foi otimizada para escalas comuns do Windows (100%–150%). Informe a
resolução e a escala do Windows no relato.

## O Windows exibe o Microsoft Defender SmartScreen

O executável beta não possui assinatura digital. Baixe-o somente da página de
[releases deste repositório](https://github.com/Deivisan/qcy-h3s-windows/releases)
e confira o nome do arquivo. Não desative permanentemente as proteções do
Windows.

## Como relatar um problema

Abra uma [issue](https://github.com/Deivisan/qcy-h3s-windows/issues/new) com
modelo, versão do Windows, adaptador Bluetooth, passos para reproduzir, resultado
esperado e resultado observado. O formulário de teste sugere quais dados
incluir. Redija MAC, serial, nome pessoal de Bluetooth e qualquer identificador.
