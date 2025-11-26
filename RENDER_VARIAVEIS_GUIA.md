# 🎯 Guia Visual: Como Adicionar Variáveis de Ambiente no Render

## 📋 Passo-a-Passo Detalhado

---

## MÉTODO 1: Durante a Criação do Serviço (Recomendado)

### Passo 1: Criar Novo Web Service

1. **Acesse:** https://render.com/dashboard
2. **Clique em:** Botão azul **"New +"** (canto superior direito)
3. **Selecione:** **"Web Service"**

```
┌────────────────────────────────────┐
│  Dashboard > New +                 │
│                                    │
│  ┌──────────────────┐             │
│  │  Web Service      │  ← CLIQUE  │
│  └──────────────────┘             │
│  ┌──────────────────┐             │
│  │  Static Site      │             │
│  └──────────────────┘             │
│  ┌──────────────────┐             │
│  │  Background Worker│             │
│  └──────────────────┘             │
└────────────────────────────────────┘
```

### Passo 2: Conectar Repositório

1. **Conecte GitHub:** Se ainda não conectou, autorize o Render a acessar seus repos
2. **Selecione o Repositório:** Procure por `bb` (seu repositório)
3. **Clique em:** Botão **"Connect"** ao lado do repo

```
┌─────────────────────────────────────────────┐
│  Select a repository                        │
│                                             │
│  🔍 Search repositories...                  │
│                                             │
│  ✓ mxalyson/bb                  [Connect]  │ ← CLIQUE
│    Trading bot repository                   │
│                                             │
└─────────────────────────────────────────────┘
```

### Passo 3: Configurar Serviço (AQUI VÃO AS VARIÁVEIS!)

Após conectar, você verá uma tela de configuração:

#### 3.1 Informações Básicas:

```
┌─────────────────────────────────────────────┐
│  Name:        trading-bot-live              │
│  Region:      Frankfurt (EU Central)        │
│  Branch:      main                          │
│  Environment: Docker                        │
└─────────────────────────────────────────────┘
```

#### 3.2 **Environment Variables** (IMPORTANTE!)

**Role a página até encontrar a seção:**

```
╔═════════════════════════════════════════════╗
║  Environment Variables                      ║
╚═════════════════════════════════════════════╝

┌─────────────────────────────────────────────┐
│                                             │
│  Add environment variables to configure     │
│  your service.                              │
│                                             │
│  [+ Add Environment Variable]  ← CLIQUE    │
│                                             │
└─────────────────────────────────────────────┘
```

**CLIQUE em:** **"+ Add Environment Variable"**

#### 3.3 Adicionar Cada Variável:

Aparecerá dois campos para cada variável:

```
┌──────────────────────────────────────────────┐
│  Key                                         │
│  ┌────────────────────────────────────────┐ │
│  │ BYBIT_API_KEY                          │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  Value                                       │
│  ┌────────────────────────────────────────┐ │
│  │ SUA_API_KEY_AQUI                       │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  [+ Add Environment Variable]                │
└──────────────────────────────────────────────┘
```

**Repita para TODAS as variáveis:**

1️⃣ **BYBIT_API_KEY**
```
Key:   BYBIT_API_KEY
Value: cole_sua_api_key_aqui
```

2️⃣ **BYBIT_API_SECRET**
```
Key:   BYBIT_API_SECRET
Value: cole_sua_api_secret_aqui
```

3️⃣ **BYBIT_TESTNET**
```
Key:   BYBIT_TESTNET
Value: false
```

4️⃣ **SYMBOL**
```
Key:   SYMBOL
Value: BTCUSDT
```

5️⃣ **TIMEFRAME**
```
Key:   TIMEFRAME
Value: 15
```

6️⃣ **MODEL_PATH**
```
Key:   MODEL_PATH
Value: storage/models/ml_model_master_scalper_365d.pkl
```

7️⃣ **MIN_ML_CONFIDENCE**
```
Key:   MIN_ML_CONFIDENCE
Value: 0.40
```

8️⃣ **RISK_PER_TRADE_PCT**
```
Key:   RISK_PER_TRADE_PCT
Value: 0.75
```

9️⃣ **SL_ATR_MULT**
```
Key:   SL_ATR_MULT
Value: 1.5
```

🔟 **TP_ATR_MULT**
```
Key:   TP_ATR_MULT
Value: 1.0
```

1️⃣1️⃣ **TRADE_COOLDOWN_SEC**
```
Key:   TRADE_COOLDOWN_SEC
Value: 900
```

1️⃣2️⃣ **DRY_RUN**
```
Key:   DRY_RUN
Value: true
```

1️⃣3️⃣ **INITIAL_CAPITAL**
```
Key:   INITIAL_CAPITAL
Value: 125.0
```

#### 3.4 Telegram (Opcional):

Se quiser notificações no Telegram:

1️⃣4️⃣ **TELEGRAM_BOT_TOKEN**
```
Key:   TELEGRAM_BOT_TOKEN
Value: seu_token_do_botfather
```

1️⃣5️⃣ **TELEGRAM_CHAT_ID**
```
Key:   TELEGRAM_CHAT_ID
Value: seu_chat_id
```

### Passo 4: Escolher Plano

```
┌─────────────────────────────────────────────┐
│  Instance Type:                             │
│                                             │
│  ○ Free           $0/month                  │
│     • Sleeps after 15 min                   │
│     • ❌ NÃO recomendado para trading       │
│                                             │
│  ● Starter        $7/month   ← ESCOLHA     │
│     • Always on                             │
│     • ✅ Recomendado                        │
│                                             │
│  ○ Standard       $25/month                 │
│     • More resources                        │
│                                             │
└─────────────────────────────────────────────┘
```

### Passo 5: Criar Serviço

**Clique em:** Botão azul **"Create Web Service"** (final da página)

**Aguarde:** 5-10 minutos para build e deploy

```
Building...
██████████████████░░░░░░░░ 75%
Building Docker image...
```

---

## MÉTODO 2: Depois da Criação do Serviço

Se já criou o serviço sem adicionar as variáveis:

### Passo 1: Acessar Seu Serviço

1. **Dashboard** → Clique no nome do seu serviço (ex: `trading-bot-live`)

### Passo 2: Ir para Environment

```
┌─────────────────────────────────────────────┐
│  trading-bot-live                           │
│  ┌─────────────────────────────────────┐   │
│  │ ⚙️ Settings                          │   │
│  │ 📊 Metrics                           │   │
│  │ 📝 Logs                              │   │
│  │ 🌍 Environment    ← CLIQUE AQUI      │   │
│  │ 💾 Disks                             │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Passo 3: Adicionar Variáveis

Na tela de Environment:

```
╔═════════════════════════════════════════════╗
║  Environment Variables                      ║
╚═════════════════════════════════════════════╝

[+ Add Environment Variable]  ← CLIQUE
```

**OU usar o Secret File (Mais Fácil!):**

```
╔═════════════════════════════════════════════╗
║  Secret Files                               ║
╚═════════════════════════════════════════════╝

[+ Add Secret File]

Filename: .env
Contents:
┌─────────────────────────────────────────────┐
│ BYBIT_API_KEY=sua_key                       │
│ BYBIT_API_SECRET=sua_secret                 │
│ BYBIT_TESTNET=false                         │
│ SYMBOL=BTCUSDT                              │
│ TIMEFRAME=15                                │
│ DRY_RUN=true                                │
│ MIN_ML_CONFIDENCE=0.40                      │
│ RISK_PER_TRADE_PCT=0.75                     │
│ SL_ATR_MULT=1.5                             │
│ TP_ATR_MULT=1.0                             │
│ TRADE_COOLDOWN_SEC=900                      │
│ INITIAL_CAPITAL=125.0                       │
└─────────────────────────────────────────────┘

[Save]
```

**Depois de adicionar, o serviço vai redeployar automaticamente!**

---

## 📝 Template Pronto para Copiar

### Para Adicionar Uma por Uma:

```
1. BYBIT_API_KEY = SUA_KEY_AQUI
2. BYBIT_API_SECRET = SUA_SECRET_AQUI
3. BYBIT_TESTNET = false
4. SYMBOL = BTCUSDT
5. TIMEFRAME = 15
6. MODEL_PATH = storage/models/ml_model_master_scalper_365d.pkl
7. MIN_ML_CONFIDENCE = 0.40
8. RISK_PER_TRADE_PCT = 0.75
9. SL_ATR_MULT = 1.5
10. TP_ATR_MULT = 1.0
11. TRADE_COOLDOWN_SEC = 900
12. DRY_RUN = true
13. INITIAL_CAPITAL = 125.0
```

### Para Secret File (.env):

**Copie e cole tudo de uma vez:**

```env
BYBIT_API_KEY=COLOQUE_SUA_KEY_AQUI
BYBIT_API_SECRET=COLOQUE_SUA_SECRET_AQUI
BYBIT_TESTNET=false
SYMBOL=BTCUSDT
TIMEFRAME=15
MODEL_PATH=storage/models/ml_model_master_scalper_365d.pkl
MIN_ML_CONFIDENCE=0.40
RISK_PER_TRADE_PCT=0.75
SL_ATR_MULT=1.5
TP_ATR_MULT=1.0
TRADE_COOLDOWN_SEC=900
DRY_RUN=true
INITIAL_CAPITAL=125.0
TELEGRAM_BOT_TOKEN=SEU_TOKEN_AQUI
TELEGRAM_CHAT_ID=SEU_CHAT_ID_AQUI
```

⚠️ **Lembre-se de substituir os valores!**

---

## ✅ Verificar se Funcionou

### Opção 1: Ver nos Logs

1. Vá em **Logs** (menu lateral)
2. Procure por:

```
✅ Variáveis carregadas:
   SYMBOL: BTCUSDT
   TIMEFRAME: 15
   DRY_RUN: true
```

### Opção 2: Verificar no Environment

1. Vá em **Environment**
2. Deve listar todas as variáveis:

```
┌──────────────────────────────────┐
│ BYBIT_API_KEY        •••••••     │
│ BYBIT_API_SECRET     •••••••     │
│ SYMBOL               BTCUSDT     │
│ TIMEFRAME            15          │
│ DRY_RUN              true        │
│ ...                              │
└──────────────────────────────────┘
```

---

## 🎬 Vídeo Tutorial (Alternativa)

Se preferir vídeo, Render tem tutoriais oficiais:
- https://render.com/docs/environment-variables

---

## ❓ FAQ

**Q: Preciso adicionar TODAS as variáveis?**
A: As essenciais são:
- BYBIT_API_KEY
- BYBIT_API_SECRET
- SYMBOL
- DRY_RUN

As outras têm valores padrão no código.

**Q: Posso editar depois?**
A: SIM! A qualquer momento em Environment → Edit

**Q: O que acontece se esquecer uma variável?**
A: O bot usará valor padrão, ou dará erro nos logs. Você pode adicionar depois.

**Q: Como proteger minhas API keys?**
A: Render oculta automaticamente os valores (mostra •••••••)

---

## 🚨 IMPORTANTE

### ⚠️ NUNCA faça commit das suas API keys!

**ERRADO ❌:**
```bash
# .env (no Git)
BYBIT_API_KEY=minha_key_real
```

**CERTO ✅:**
```bash
# .env (no Git)
BYBIT_API_KEY=sua_key_aqui

# Adicionar no Render via interface web!
```

---

**Dúvidas?** Me avise que explico melhor! 😊
