# BLE no Windows: conexão já conhecida e estado do fone

## O problema reproduzido

O H3S já foi conectado com sucesso a um endereço BLE previamente identificado,
mesmo quando o `BleakScanner.discover()` não encontrava anúncio do fone. Com o
endereço em forma de `str`, o Bleak/WinRT inicia uma descoberta implícita antes
de conectar e retorna `BleakDeviceNotFoundError` se o headset está conhecido,
mas não está anunciando.

O endereço clássico exibido pelo Windows pode ser diferente e não deve ser
usado como endereço GATT BLE. Endereços identificadores foram omitidos desta
documentação pública.

## Caminho aplicado

1. Se o app já tem um link BLE ativo, o diálogo de scan mostra esse link em
   primeiro lugar e não inicia outra descoberta.
2. Para dispositivos recebidos pelo scan, preservar o `BLEDevice` do Bleak e
   passá-lo ao `BleakClient` (evita uma segunda descoberta implícita).
3. Após uma conexão bem-sucedida, guardar localmente o último endereço BLE usado.
   Em buscas futuras, oferecer esse endereço como fallback e construir um
   `BLEDevice` WinRT para resolver o cache sem depender de novo anúncio.
4. A tentativa de conexão, e não a presença no scan ou o pareamento clássico,
   determina se o link GATT está realmente disponível.

O endereço salvo fica nas configurações locais do aplicativo no perfil Windows
do usuário; não é enviado para servidor algum. Uma instalação nova não contém
MAC de headset embutido.

O callback de desconexão do Bleak recebe o cliente que caiu. O worker associa
esse callback à instância que abriu a conexão; callback atrasado de uma conexão
antiga não pode apagar uma conexão nova.

## Verificação feita

Em 30/10/2026, com o H3S fora do scan BLE:

- conectar pelo endereço salvo como `str`: `BleakDeviceNotFoundError`;
- conectar com `BLEDevice` WinRT construído a partir do endereço salvo: sucesso;
- handshake RCSP: sucesso;
- leitura ANC: `0`;
- leitura de modo de áudio `0x2E`: `0`;
- leitura de bateria: `90%`;
- desconexão explícita: cliente desconectado.

## Limites de feedback

O firmware H3S pode ecoar comandos ANC inválidos em `GET 0x17`; esse eco não é
prova de aplicação. O app não deve afirmar que o modo foi confirmado apenas
porque recebeu o eco. A troca de cena `0x2E` tem read-back e pode ser confirmada;
Game Mode tem read-back por `GET_ADV_INFO`. A fala/aviso audível é gerada pelo
firmware do fone, não pelo app, e pode não ocorrer em todos os estados/volumes.
