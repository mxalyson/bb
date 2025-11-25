# 🚀 Bot Setup Checklist

## ✅ Pre-Flight Checklist

### 1. **Arquivos Necessários**
- [ ] `live_bot.py` - Bot principal
- [ ] `ml_model_master_scalper_365d.pkl` - Modelo ML treinado
- [ ] `.env` - Configuração (copiar de `.env.example`)
- [ ] `core/` - Módulos core (data, features, bybit_rest, etc.)
- [ ] `requirements.txt` - Dependências Python

### 2. **Configuração do Ambiente**

```bash
# Instalar dependências
pip install -r requirements.txt

# Copiar e configurar .env
cp .env.example .env
nano .env  # ou vim/code .env
```

### 3. **Configurar .env**

**Obrigatório:**
- `BYBIT_API_KEY` - Sua API key da Bybit
- `BYBIT_API_SECRET` - Seu API secret da Bybit
- `DRY_RUN=true` - Começar em paper trading
- `BYBIT_TESTNET=true` - Usar testnet primeiro

**Recomendado:**
- `TELEGRAM_BOT_TOKEN` - Para notificações
- `TELEGRAM_CHAT_ID` - Seu chat ID

### 4. **Testar Configuração**

```bash
# Testar import
python3 -c "from live_bot import LiveTradingBot; print('✅ OK')"

# Testar modelo
python3 -c "import pickle; m = pickle.load(open('ml_model_master_scalper_365d.pkl', 'rb')); print('✅ Model OK')"

# Verificar .env
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print(f'Symbol: {os.getenv(\"SYMBOL\")}'); print('✅ .env OK')"
```

### 5. **Primeira Execução (Testnet)**

```bash
# Verificar se está em modo seguro
grep "DRY_RUN=true" .env && grep "BYBIT_TESTNET=true" .env && echo "✅ Safe mode"

# Rodar bot
python3 live_bot.py
```

### 6. **Monitorar Logs**

Você deve ver:
```
🚀 LIVE TRADING BOT - SNIPER MODE
Symbol: BTCUSDT
Timeframe: 15m
Mode: 🔵 DRY RUN
Exchange: TESTNET
💓 Heartbeat #1 | UTC: 12:34:56 | Status: No position
⏳ Vela fecha em 543s (9.1min)...
```

### 7. **Comandos Telegram** (se configurado)

- `/help` - Listar comandos
- `/status` - Status do bot
- `/position` - Posição aberta
- `/capital` - Capital atual
- `/pause` - Pausar bot
- `/resume` - Retomar bot
- `/setconf 40` - Mudar confiança mínima
- `/setrisk 0.75` - Mudar risco por trade

---

## ⚠️ Antes de ir LIVE

### Checklist LIVE Trading:

- [ ] Testou no testnet por pelo menos 24h
- [ ] Verificou que predições estão funcionando
- [ ] Telegram notificações funcionando
- [ ] Heartbeat aparecendo a cada 5min
- [ ] Sem erros nos logs por 24h
- [ ] Entende os riscos de trading real
- [ ] Capital inicial está correto no .env
- [ ] Configurou stop loss adequado

### Mudar para LIVE:

```bash
# Editar .env
nano .env

# Alterar:
DRY_RUN=false
BYBIT_TESTNET=false

# ⚠️ ATENÇÃO: Agora é DINHEIRO REAL!
```

---

## 🛡️ Proteções Implementadas

### 1. **Timeout Protection**
- Download de dados: timeout de 120s
- Previne travamento em API calls lentas

### 2. **Heartbeat/Watchdog**
- Log a cada 5 minutos mostrando que está vivo
- Notificação Telegram a cada hora
- Você sempre saberá se o bot está rodando

### 3. **Circuit Breaker**
- Detecta erros consecutivos
- Exponential backoff: 30s → 60s → 90s → 120s → 150s
- Após 5 erros: alerta Telegram + wait 5min

### 4. **Smart Wait**
- Espera adaptativa baseada no tempo até próxima vela
- Reduz API calls em 97% (de ~8.600 para ~200-300/dia)
- Cache inteligente de dados

### 5. **Position Recovery**
- Se o bot reiniciar, recupera posições abertas na Bybit
- Continua monitorando SL/TP

---

## 📊 Monitoramento

### Logs Esperados:

**Normal Operation:**
```
💓 Heartbeat #42 | UTC: 03:15:22 | Status: No position
⏳ Vela fecha em 543s (9.1min) - aguardando mais 120s...
🔍 Vela fechou - baixando dados...
📥 Baixando dados com timeout de 120s...
📥 Downloaded 2892 candles
⚙️ Construindo features...
✅ Features ready: (2831, 80)
🔮 Fazendo predição para candle 2025-11-25 08:15:00...
🔮 Previsão: 0.521 | Sinal: NEUTRO | Confiança: 4.1%
⏭️ Sinal NEUTRO - pulando
```

**Position Open:**
```
🟢 ABRINDO POSIÇÃO LONG
Preço: $87,366.30
Confiança: 45.2%
Qtd: 0.001 BTC = $87.37
🛑 SL: $86,500.00 (-1.0%)
🎯 TP: $87,800.00 (+0.5%)
```

**Error Recovery:**
```
❌ Error in main loop (#1): Connection error
⏳ Waiting 30s before retry...
✅ Recovered from errors (was 1 consecutive)
```

---

## 🐛 Troubleshooting

### Bot não inicia:
```bash
# Verificar Python
python3 --version  # Precisa 3.8+

# Verificar dependências
pip install -r requirements.txt

# Verificar imports
python3 -c "import lightgbm, pandas, numpy; print('OK')"
```

### Erro de API:
```bash
# Testar conexão Bybit
python3 -c "from core.bybit_rest import BybitRESTClient; import os; from dotenv import load_dotenv; load_dotenv(); client = BybitRESTClient(os.getenv('BYBIT_API_KEY'), os.getenv('BYBIT_API_SECRET'), testnet=True); print(client.get_server_time())"
```

### Telegram não funciona:
```bash
# Testar token
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"

# Testar chat_id
curl "https://api.telegram.org/bot<YOUR_TOKEN>/sendMessage?chat_id=<YOUR_CHAT_ID>&text=Test"
```

### Bot travado:
- Verificar logs
- Procurar por última linha de "Heartbeat"
- Se não há heartbeat por >10min, processo pode estar suspenso
- Restart: `Ctrl+C` e rodar novamente

---

## 📞 Suporte

- **Logs:** Sempre salve logs quando reportar problemas
- **Telegram:** Use `/status` para debug rápido
- **GitHub Issues:** Reporte bugs com logs completos

---

## ⚡ Performance Esperada

### Baseado no modelo `ml_model_master_scalper_365d.pkl`:

- **ROI:** 2788% em 365 dias (backtest)
- **Win Rate:** ~55-60%
- **Trades/dia:** Varia (depende de sinais)
- **SL/TP Ratio:** 2.0x ATR / 0.7x ATR
- **Confiança mínima:** 25%

⚠️ **IMPORTANTE:** Performance passada não garante resultados futuros!

---

Good luck! 🚀
