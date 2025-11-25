# 🔌 WebSocket para Trading Bot - Análise Completa

## 📊 Situação Atual (Polling)

### Como Funciona Agora:
```python
while True:
    # 1. Baixa dados a cada 30s
    df = download_data()

    # 2. Verifica se é novo candle
    current_candle = df.iloc[-2]
    if current_candle != last_candle:
        # Novo candle! Fazer predição

    # 3. Espera 30s
    time.sleep(30)
```

### Problemas:
- ❌ **Latência:** Pode demorar até 30s para detectar novo candle
- ❌ **Rate Limit:** Faz muitas requisições desnecessárias
- ❌ **Ineficiente:** 99% das requisições retornam dados já conhecidos
- ❌ **Custo:** Consome mais bandwidth

---

## 🚀 Solução com WebSocket

### Como Funcionaria:
```python
# 1. Conectar WebSocket
ws = connect_websocket("wss://stream.bybit.com/v5/public/linear")

# 2. Subscrever ao canal de klines
ws.subscribe("kline.15.BTCUSDT")

# 3. Receber eventos em tempo real
@ws.on_message
def on_candle_update(data):
    candle = data['candle']

    if candle['confirm']:  # Candle fechou!
        # Aguardar consolidação
        time.sleep(60)

        # Fazer predição
        make_prediction(candle)
```

### Vantagens:
- ✅ **Real-time:** Recebe notificação IMEDIATA quando candle fecha
- ✅ **Eficiente:** Apenas 1 conexão ativa, sem polling
- ✅ **Rate Limit:** Economiza centenas de requisições REST
- ✅ **Latência:** ~1-2s vs ~30s do polling
- ✅ **Custo:** Menos bandwidth

---

## 🔧 Implementação Técnica

### 1. Biblioteca: `websocket-client` ou `python-bybit`

```bash
pip install websocket-client
# ou
pip install pybit
```

### 2. Estrutura Básica:

```python
import websocket
import json
import threading

class BybitWebSocket:
    def __init__(self, symbol: str, interval: str):
        self.symbol = symbol
        self.interval = interval
        self.ws = None

    def on_message(self, ws, message):
        """Callback quando recebe mensagem"""
        data = json.loads(message)

        if 'data' in data:
            # Processar dados do candle
            self.handle_candle(data['data'])

    def on_error(self, ws, error):
        """Callback de erro"""
        print(f"WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Callback ao fechar"""
        print("WebSocket closed, reconnecting...")
        self.connect()  # Reconectar automaticamente

    def on_open(self, ws):
        """Callback ao abrir conexão"""
        # Subscrever ao canal de klines
        subscribe_msg = {
            "op": "subscribe",
            "args": [f"kline.{self.interval}.{self.symbol}"]
        }
        ws.send(json.dumps(subscribe_msg))

    def handle_candle(self, candle_data):
        """Processa dados do candle"""
        candle = candle_data[0]

        # Verificar se candle fechou
        if candle.get('confirm', False):
            print(f"🆕 Candle fechou: {candle['start']}")

            # Aguardar consolidação
            time.sleep(60)

            # Fazer predição com dados consolidados
            self.make_prediction()

    def connect(self):
        """Conectar ao WebSocket"""
        url = "wss://stream.bybit.com/v5/public/linear"

        self.ws = websocket.WebSocketApp(
            url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

        # Rodar em thread separada
        ws_thread = threading.Thread(target=self.ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()
```

### 3. Uso no Bot:

```python
# Inicializar WebSocket
ws = BybitWebSocket("BTCUSDT", "15")
ws.connect()

# Bot continua rodando, WebSocket notifica quando candle fecha
while True:
    # Apenas monitorar posições abertas
    if position:
        check_position_exit()

    time.sleep(5)  # Menos frequente, WebSocket cuida dos candles
```

---

## ⚠️ Desafios e Soluções

### 1. Reconexão Automática

**Problema:** WebSocket pode desconectar

**Solução:**
```python
def on_close(self, ws, close_status_code, close_msg):
    logger.warning("WebSocket closed, reconnecting in 5s...")
    time.sleep(5)
    self.connect()
```

### 2. Heartbeat/Ping

**Problema:** Conexão pode ficar idle e ser fechada

**Solução:**
```python
def send_ping(self):
    """Enviar ping a cada 20s"""
    while True:
        if self.ws:
            self.ws.send(json.dumps({"op": "ping"}))
        time.sleep(20)
```

### 3. Dados Ainda Precisam de Consolidação

**Importante:** Mesmo com WebSocket, os dados podem não estar consolidados imediatamente!

**Solução:** Manter buffer de 60s MESMO com WebSocket
```python
if candle.get('confirm'):
    logger.info("Candle fechou via WebSocket")
    logger.info("Aguardando 60s para consolidação...")
    time.sleep(60)

    # Baixar dados consolidados via REST
    df = download_data_rest()
    make_prediction(df)
```

### 4. Fallback para REST

**Problema:** Se WebSocket falhar

**Solução:** Sistema híbrido
```python
class HybridDataSource:
    def __init__(self):
        self.websocket = BybitWebSocket()
        self.rest_backup = True
        self.last_candle_time = None

    def run(self):
        # Tentar WebSocket primeiro
        try:
            self.websocket.connect()
        except:
            logger.warning("WebSocket failed, using REST polling")
            self.rest_backup = True

        while True:
            # Se WebSocket não está funcionando, usar polling
            if self.rest_backup:
                self.poll_rest()

            time.sleep(5)
```

---

## 📊 Comparação: Polling vs WebSocket

| Métrica | Polling (Atual) | WebSocket |
|---------|----------------|-----------|
| **Latência** | ~30s | ~1-2s |
| **Requisições/hora** | ~120 | ~1-2 |
| **Rate Limit** | Alto risco | Baixo risco |
| **Complexidade** | Simples | Média |
| **Confiabilidade** | Alta | Média (precisa reconexão) |
| **Consolidação** | Precisa buffer 60s | Precisa buffer 60s (igual!) |
| **Vantagem** | - | ✅ Tempo real + Economia |

---

## 🎯 Recomendação

### Implementar Sistema Híbrido:

```python
class SmartDataManager:
    def __init__(self):
        self.websocket = BybitWebSocket()
        self.rest_client = BybitRESTClient()
        self.mode = "websocket"  # ou "polling"

    def start(self):
        # Tentar WebSocket
        try:
            self.websocket.on_candle_close = self.on_new_candle
            self.websocket.connect()
            self.mode = "websocket"
            logger.info("✅ Using WebSocket (real-time)")
        except:
            self.mode = "polling"
            logger.warning("⚠️ WebSocket failed, using REST polling")

    def on_new_candle(self, candle_time):
        """Callback quando candle fecha (via WebSocket OU polling)"""
        logger.info(f"🆕 New candle: {candle_time}")

        # Buffer de consolidação (SEMPRE!)
        logger.info("⏳ Waiting 60s for consolidation...")
        time.sleep(60)

        # Baixar dados consolidados via REST
        df = self.rest_client.get_data()

        # Fazer predição
        self.make_prediction(df)
```

**Vantagens:**
- ✅ Usa WebSocket quando disponível (rápido, eficiente)
- ✅ Fallback para polling se WebSocket falhar (confiável)
- ✅ Mantém buffer de 60s (dados consolidados)
- ✅ Melhor de ambos os mundos!

---

## 🚀 Implementação Sugerida

### Fase 1: Protótipo WebSocket (1-2 dias)
- [ ] Criar classe BybitWebSocket básica
- [ ] Testar conexão e subscrição
- [ ] Verificar se detecta candle fechado corretamente
- [ ] Comparar latência vs polling

### Fase 2: Integração (2-3 dias)
- [ ] Integrar WebSocket ao live_bot.py
- [ ] Implementar reconexão automática
- [ ] Implementar heartbeat/ping
- [ ] Testar estabilidade 24h

### Fase 3: Sistema Híbrido (1-2 dias)
- [ ] Criar fallback para REST
- [ ] Auto-switch se WebSocket falhar
- [ ] Logs para monitorar qual modo está ativo
- [ ] Testes de stress

### Fase 4: Produção (1 dia)
- [ ] Configuração via env vars (WS_ENABLED=true/false)
- [ ] Documentação
- [ ] Deploy e monitoramento

**Total estimado: ~1 semana de desenvolvimento**

---

## 💡 Conclusão

**VALE MUITO A PENA implementar WebSocket!**

### Benefícios:
- ✅ 30s → 1-2s de latência (15x mais rápido!)
- ✅ ~120 → ~2 requisições/hora (60x menos!)
- ✅ Economia de rate limit
- ✅ Mais profissional

### Complexidade:
- ⚠️ Média (reconexão, heartbeat, fallback)
- ⚠️ Mas bibliotecas prontas facilitam muito

### Recomendação Final:
**SIM, implementar!** Começar com protótipo simples e evoluir para sistema híbrido.

---

## 📚 Recursos

- **Bybit WebSocket Docs:** https://bybit-exchange.github.io/docs/v5/ws/connect
- **Python Library:** `pip install pybit` (já tem WebSocket integrado!)
- **Exemplo de código:** [Ver protótipo abaixo]

---

*Análise: 2025-11-25*
*Prioridade: ALTA*
*Complexidade: MÉDIA*
*Tempo estimado: 1 semana*
