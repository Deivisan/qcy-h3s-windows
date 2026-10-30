# Servidor MCP opcional

O servidor `mcp_server.py` é uma interface separada da aplicação gráfica. Para
evitar gravar no repositório o endereço BLE pessoal de uma unidade, ele usa a
variável de ambiente `QCY_H3_BLE_ADDRESS` quando definida. Sem ela, tenta
identificar exatamente um H3/H3S no scan; se houver zero ou vários candidatos,
encerra com orientação em vez de escolher um dispositivo ambíguo.

No PowerShell, para a sessão atual:

```powershell
$env:QCY_H3_BLE_ADDRESS = "AA:BB:CC:DD:EE:FF"
python mcp_server.py
```

O valor é um exemplo: substitua pelo endereço **BLE/GATT** obtido no seu PC, não
necessariamente pelo endereço clássico mostrado nas Configurações Bluetooth.
Não faça commit de um MAC pessoal nem compartilhe esse valor em logs/issues.
O aplicativo desktop salva localmente o último endereço BLE conectado nas
configurações do usuário do Windows para reconexões futuras.
