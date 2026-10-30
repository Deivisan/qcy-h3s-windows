# Roteiro de teste da beta

Objetivo: verificar operação cotidiana do Controle QCY H3 em PCs, adaptadores,
firmwares e nos dois modelos-alvo. Este roteiro não substitui validação de
segurança nem certificação do fabricante.

## Antes de começar

- Registre o modelo exato: **QCY H3** ou **QCY H3S**.
- Registre Windows (10/11, edição/build) e, se disponível, fabricante/modelo do
  adaptador Bluetooth.
- Feche o app oficial da QCY e outros controladores BLE enquanto testa.
- Não publique endereço BLE/MAC, serial ou seu nome pessoal de Bluetooth.

## Lista de verificação

| Teste | Resultado |
|---|---|
| Aplicativo abre sem dependências Python | ☐ |
| Busca encontra o headset ligado | ☐ |
| Conexão BLE completa e bateria aparece | ☐ |
| Mudar ANC/transparência/adaptativo produz mudança audível | ☐ |
| Game Mode alterna e volta ao estado esperado | ☐ |
| EQ atual é lido na conexão | ☐ |
| Ajuste/preset é aplicado e persiste após nova leitura | ☐ |
| Desconectar e reconectar atualiza o estado | ☐ |
| Ajuda e atalhos funcionam | ☐ |

Para verificar EQ, preserve seus valores atuais e anote-os antes de mexer.
Faça somente um pequeno ajuste temporário se estiver confortável, use **Aplicar
EQ**, observe o status/read-back e restaure sua configuração original. O EQ pode
afetar bastante a audição; não use níveis altos para testar.

## Modelo de relato

```text
Modelo: QCY H3 / QCY H3S
Firmware (se conhecido):
Windows (versão/build):
Adaptador Bluetooth (fabricante/modelo, se conhecido):
Versão do app: 0.1.1-beta
Teste que falhou:
Passos para reproduzir:
Esperado:
Observado:
O app oficial/outro controlador estava aberto? sim/não
```

Remova MAC, serial, IDs do dispositivo, nome pessoal de Bluetooth e capturas
que mostrem informações privadas. Abra uma [issue no GitHub](https://github.com/Deivisan/qcy-h3s-windows/issues/new)
e relate somente o necessário.
