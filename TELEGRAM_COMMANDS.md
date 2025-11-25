# 📱 Comandos do Telegram - Controle Total do Bot

## ✅ Sim! Você pode controlar TUDO via Telegram

O bot já tem comandos implementados que permitem alterar configurações em tempo real, sem precisar parar o bot ou editar código!

---

## 📋 Lista Completa de Comandos

### 📊 **Informações**

#### `/status`
Ver status geral do bot
```
🤖 Status do Bot

Estado: ▶️ ATIVO
Modo: 🔴 LIVE
Network: TESTNET
Symbol: BTCUSDT
Timeframe: 15m

⚙️ Config:
Confiança Min: 25%
Risco/Trade: 0.50%
SL: 3.0x ATR
TP: 6.0x ATR
Cooldown: 15min
```

#### `/config`
Ver TODAS as configurações atuais
```
⚙️ Configurações Atuais

Trading:
Confiança Min: 25%
Risco/Trade: 0.50%
Stop Loss: 3.0x ATR
Take Profit: 6.0x ATR
Cooldown: 15min

Modelo:
Threshold: 0.500
Timeframe: 15m

Sistema:
Modo: 🔴 LIVE
Network: TESTNET
Estado: ▶️ ATIVO
```

#### `/position`
Ver posição aberta atual
```
🟢 Posição LONG

Entrada: $87,450.00
Atual: $87,680.00
Qtd: 0.012 BTC

🟢 PnL: +0.26% (+$2.76)
Duração: 2h 15m

🛑 SL: $87,100.00
🎯 TP: $88,200.00
📊 Confiança: 35%
```

#### `/capital`
Ver capital atual
```
💰 Capital

Atual: $1,012.50
Inicial: $1,000.00
Variação: +1.25%
```

---

### ⚙️ **Controle**

#### `/pause`
Pausar bot (não abre novos trades)
```
⏸️ Bot Pausado

Não abrirá novos trades.
Posições abertas continuam sendo monitoradas.

Use /resume para retomar.
```

#### `/resume`
Retomar bot
```
▶️ Bot Retomado

Voltará a abrir trades conforme sinais.
```

#### `/forcecheck`
Forçar verificação de novo candle
```
🔄 Verificação Forçada

O bot verificará novo candle na próxima iteração.
```

---

### 🔧 **Configuração em Tempo Real**

#### `/setconf <0-100>`
Mudar confiança mínima (%)

**Exemplos:**
```
/setconf 25  → Exige 25% de confiança mínima
/setconf 35  → Exige 35% de confiança mínima (mais conservador)
/setconf 15  → Exige 15% de confiança mínima (mais agressivo)
```

**Resposta:**
```
✅ Confiança Atualizada

25% → 35%
```

#### `/setrisk <0.1-2.0>`
Mudar risco por trade (%)

**Exemplos:**
```
/setrisk 0.5  → Arrisca 0.5% do capital por trade
/setrisk 1.0  → Arrisca 1.0% do capital por trade
/setrisk 0.3  → Arrisca 0.3% do capital por trade (conservador)
```

**Resposta:**
```
✅ Risco Atualizado

0.50% → 1.00%
```

#### `/setsl <1-10>`
Mudar Stop Loss (x ATR)

**Exemplos:**
```
/setsl 3.0  → SL a 3x ATR
/setsl 2.5  → SL a 2.5x ATR (mais apertado, menos risco)
/setsl 4.0  → SL a 4x ATR (mais largo, mais risco)
```

**Resposta:**
```
✅ Stop Loss Atualizado

3.0x → 2.5x ATR
```

#### `/settp <1-20>`
Mudar Take Profit (x ATR)

**Exemplos:**
```
/settp 6.0  → TP a 6x ATR
/settp 8.0  → TP a 8x ATR (mais ganância)
/settp 4.0  → TP a 4x ATR (mais conservador)
```

**Resposta:**
```
✅ Take Profit Atualizado

6.0x → 8.0x ATR
```

#### `/setcooldown <5-120>`
Mudar cooldown entre trades (minutos)

**Exemplos:**
```
/setcooldown 15  → 15min entre trades
/setcooldown 30  → 30min entre trades (mais conservador)
/setcooldown 5   → 5min entre trades (mais agressivo)
```

**Resposta:**
```
✅ Cooldown Atualizado

15min → 30min
```

---

## 🎯 Casos de Uso Práticos

### 1. **Mercado Muito Volátil**
```
/setconf 40        → Exige mais confiança
/setsl 4.0         → SL mais largo
/setcooldown 30    → Espera mais entre trades
```

### 2. **Mercado Lateral (Range)**
```
/settp 4.0         → TP mais próximo
/setsl 2.5         → SL mais apertado
/setconf 30        → Confiança moderada
```

### 3. **Mercado Tendência Forte**
```
/settp 8.0         → TP mais distante
/setconf 25        → Aceita sinais com menos confiança
/setcooldown 15    → Mais trades
```

### 4. **Hora de Dormir (Conservador)**
```
/pause             → Para de abrir novos trades
                     (posições abertas continuam sendo monitoradas)
```

### 5. **Acordou (Retomar)**
```
/resume            → Volta a abrir trades
/status            → Verifica estado
```

### 6. **Teste Rápido**
```
/forcecheck        → Força verificação de candle
                     (útil para testar se bot está funcionando)
```

---

## 📊 Monitoramento Contínuo

### Rotina Recomendada:

**Manhã:**
```
/status            → Ver estado geral
/position          → Ver se tem posição aberta
/capital           → Ver capital
```

**Durante o dia:**
- Bot envia notificações automáticas de trades
- Você pode ajustar configs conforme mercado muda

**Noite:**
```
/config            → Ver todas as configs
/pause             → Pausar se quiser (opcional)
```

---

## 🚨 Notificações Automáticas

O bot SEMPRE envia notificações para:

✅ **Abertura de Trade:**
```
🟢 LONG ABERTO

Entrada: $87,450.00
Qtd: 0.012 BTC
SL: $87,100.00 (-2.5%)
TP: $88,200.00 (+5.0%)
Confiança: 35%
```

✅ **Fechamento de Trade:**
```
✅ LONG FECHADO - TAKE PROFIT

Entrada: $87,450.00
Saída: $88,200.00
PnL: +5.0% (+$52.50)
Duração: 3h 45m
```

✅ **Heartbeat (a cada hora):**
```
💓 Bot Alive

Loop #156
Status: No position
```

✅ **Erros:**
```
🚨 ALERTA: Bot com problemas

5 erros consecutivos

Último erro:
Connection timeout...
```

---

## 💡 Dicas Importantes

### ✅ **Sim, pode alterar durante o bot rodando!**
- Todas as mudanças são IMEDIATAS
- Não precisa reiniciar o bot
- Configurações são aplicadas na próxima verificação

### ⚠️ **Limites de Segurança**
Todos os comandos têm limites para evitar erros:
- Confiança: 0-100%
- Risco: 0.1-2.0%
- SL: 1-10x ATR
- TP: 1-20x ATR
- Cooldown: 5-120min

### 📝 **Logs**
Todas as mudanças são logadas:
```
2025-11-25 10:30:15 [INFO] ⚙️ Confiança alterada via Telegram: 25% → 35%
2025-11-25 10:31:42 [INFO] ⚙️ Risco alterado via Telegram: 0.50% → 1.00%
```

---

## 🎯 Exemplo de Conversa Real

**Você no Telegram:**
```
/status
```

**Bot responde:**
```
🤖 Status do Bot

Estado: ▶️ ATIVO
Modo: 🔴 LIVE
...
Confiança Min: 25%
```

**Você:**
```
/setconf 35
```

**Bot:**
```
✅ Confiança Atualizada

25% → 35%
```

**Você:**
```
/config
```

**Bot:**
```
⚙️ Configurações Atuais

Trading:
Confiança Min: 35%  ← Mudou!
...
```

---

## ✅ Conclusão

**SIM! Você tem CONTROLE TOTAL via Telegram:**

✅ Ver status em tempo real
✅ Pausar/retomar bot
✅ Alterar TODAS as configurações
✅ Forçar verificações
✅ Monitorar posições e capital
✅ Receber notificações automáticas

**Sem precisar:**
❌ Parar o bot
❌ Editar código
❌ Editar arquivos .env
❌ Reiniciar nada

**Tudo em tempo real, direto do celular!** 📱

---

*Documentação atualizada - 2025-11-25*
