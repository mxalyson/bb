# 🚀 Guia Completo de Deploy - Render & Railway

## 📋 Pré-requisitos

- [x] Conta no [Render](https://render.com) ou [Railway](https://railway.app)
- [x] Repositório Git (GitHub, GitLab, ou Bitbucket)
- [x] API Keys da Bybit
- [x] Modelo treinado (ml_model_master_scalper_365d.pkl)

---

## 🎯 OPÇÃO 1: Deploy no Render

### Passo 1: Preparar o Projeto

#### 1.1 Verificar Arquivos Necessários

✅ Seu projeto JÁ TEM:
- `Dockerfile` ✅
- `requirements.txt` ✅
- `.dockerignore` ✅

#### 1.2 Fazer Push para GitHub

```bash
git add .
git commit -m "Preparar para deploy no Render"
git push origin main
```

### Passo 2: Criar Serviço no Render

#### 2.1 Acessar Dashboard

1. Acesse https://render.com
2. Faça login
3. Clique em **"New +"** → **"Web Service"**

#### 2.2 Conectar Repositório

1. Conecte sua conta GitHub/GitLab
2. Selecione o repositório `bb`
3. Clique em **"Connect"**

#### 2.3 Configurar Serviço

**Configurações básicas:**
- **Name:** `trading-bot-live` (ou qualquer nome)
- **Region:** Escolha o mais próximo (ex: `Frankfurt`)
- **Branch:** `main` (ou sua branch principal)
- **Root Directory:** (deixe em branco)
- **Environment:** `Docker`
- **Dockerfile Path:** `./Dockerfile` (padrão)

**Plan:**
- **Free:** Limitado, dorme após 15min de inatividade ❌
- **Starter ($7/mês):** Recomendado - sempre ativo ✅
- **Standard ($25/mês):** Mais recursos

### Passo 3: Configurar Variáveis de Ambiente

Na seção **"Environment Variables"**, adicione:

```bash
# Bybit API
BYBIT_API_KEY=sua_api_key_aqui
BYBIT_API_SECRET=sua_api_secret_aqui
BYBIT_TESTNET=false

# Trading
SYMBOL=BTCUSDT
TIMEFRAME=15
MODEL_PATH=storage/models/ml_model_master_scalper_365d.pkl

# Risk Management
MIN_ML_CONFIDENCE=0.40
RISK_PER_TRADE_PCT=0.75
SL_ATR_MULT=1.5
TP_ATR_MULT=1.0
TRADE_COOLDOWN_SEC=900

# Mode
DRY_RUN=true
INITIAL_CAPITAL=125.0

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=seu_token_aqui
TELEGRAM_CHAT_ID=seu_chat_id_aqui
```

### Passo 4: Deploy!

1. Clique em **"Create Web Service"**
2. Aguarde o build (~5-10 minutos)
3. Logs aparecerão em tempo real

**Você verá:**
```
Starting deployment...
Building Docker image...
Successfully built image
Starting service...
✅ Service is live!
```

### Passo 5: Monitorar Logs

1. Clique na aba **"Logs"**
2. Veja os logs em tempo real:

```
📌 Detected model type: V1
✅ Using WebSocket (real-time)
🚀 Starting trading loop...
```

### Passo 6: Configurar Persistent Storage (IMPORTANTE!)

⚠️ **Por padrão, o Render NÃO persiste arquivos!**

Para manter o estado do bot entre restarts:

1. Vá em **"Environment"** → **"Disks"**
2. Clique em **"Add Disk"**
3. Configure:
   - **Name:** `storage`
   - **Mount Path:** `/app/storage`
   - **Size:** `1 GB` (suficiente)
4. Clique em **"Save"**

Agora o bot manterá:
- Estado de trades
- Histórico de predições
- Modelos

---

## 🎯 OPÇÃO 2: Deploy no Railway

### Passo 1: Preparar o Projeto

Mesmos arquivos do Render! ✅

### Passo 2: Criar Projeto no Railway

#### 2.1 Acessar Dashboard

1. Acesse https://railway.app
2. Faça login com GitHub
3. Clique em **"New Project"**

#### 2.2 Deploy from GitHub

1. Selecione **"Deploy from GitHub repo"**
2. Escolha seu repositório `bb`
3. Railway detectará automaticamente o Dockerfile

### Passo 3: Configurar Variáveis de Ambiente

1. Clique no serviço criado
2. Vá em **"Variables"**
3. Clique em **"RAW Editor"**
4. Cole:

```bash
BYBIT_API_KEY=sua_api_key_aqui
BYBIT_API_SECRET=sua_api_secret_aqui
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

TELEGRAM_BOT_TOKEN=seu_token_aqui
TELEGRAM_CHAT_ID=seu_chat_id_aqui
```

### Passo 4: Deploy!

1. Railway fará deploy automático
2. Aguarde build (~3-5 minutos)
3. Bot iniciará automaticamente

### Passo 5: Monitorar Logs

1. Clique em **"Deployments"**
2. Clique no deployment ativo
3. Veja logs em tempo real

### Passo 6: Configurar Volume (IMPORTANTE!)

⚠️ **Railway TAMBÉM não persiste por padrão!**

1. Vá em **"Settings"** → **"Volumes"**
2. Clique em **"New Volume"**
3. Configure:
   - **Mount Path:** `/app/storage`
4. Clique em **"Add"**

---

## 📊 Comparação: Render vs Railway

| Feature | Render | Railway |
|---------|--------|---------|
| **Preço Free** | $0 (mas dorme) | $5 crédito/mês |
| **Preço Starter** | $7/mês | ~$5-10/mês |
| **Deploy** | Manual (push) | Auto (GitHub) |
| **Logs** | Bons | Excelentes |
| **Persistent Storage** | Disks (pago) | Volumes (grátis) |
| **Health Checks** | Sim | Sim |
| **Auto-restart** | Sim | Sim |
| **Facilidade** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**Recomendação:**
- **Railway** para começar (mais fácil, volumes grátis)
- **Render** para produção (mais estável)

---

## ⚙️ Configurações Avançadas

### 1. Auto-Deploy no Git Push

**Render:**
- Já ativo por padrão! ✅
- Push para `main` → deploy automático

**Railway:**
- Já ativo por padrão! ✅

### 2. Health Checks

Já configurado no Dockerfile:
```dockerfile
HEALTHCHECK --interval=60s --timeout=10s \
    CMD python -c "import sys; sys.exit(0)"
```

### 3. Resource Limits

**Railway:**
```bash
# Limitar memória
railway up --memory 512
```

**Render:**
- Configurar no dashboard: Settings → Resources

### 4. Logs Externos (opcional)

**Integrar com Better Stack / Datadog:**

```python
# Em live_bot.py
import logging
from logging.handlers import HTTPHandler

handler = HTTPHandler(
    'logs.betterstack.com',
    '/api/v1/logs',
    method='POST'
)
logger.addHandler(handler)
```

---

## 🐛 Troubleshooting

### Problema 1: Bot não inicia

**Solução:**
1. Verificar logs: `ModuleNotFoundError`?
2. Checar `requirements.txt`
3. Rebuild: `git commit --allow-empty -m "rebuild" && git push`

### Problema 2: Conexão com Bybit falha

**Solução:**
1. Verificar API keys corretas
2. Testar em local primeiro:
   ```bash
   docker build -t bot .
   docker run --env-file .env bot
   ```

### Problema 3: Modelo não encontrado

**Solução:**
1. Fazer upload do modelo:
   ```bash
   # Via Git LFS (se modelo > 100MB)
   git lfs track "*.pkl"
   git add .gitattributes storage/models/*.pkl
   git commit -m "Add model"
   git push
   ```

2. Ou usar URL externa:
   ```python
   # Baixar modelo na inicialização
   if not os.path.exists(MODEL_PATH):
       download_from_s3(MODEL_PATH)
   ```

### Problema 4: Estado perdido após restart

**Solução:**
- Configurar Persistent Storage (ver Passo 6 acima)

---

## 📱 Monitoramento

### 1. Telegram Notifications

Já configurado! Receba alertas:
- 🆕 Novo candle
- 🔮 Predições
- 💰 Trades
- ❌ Erros

### 2. Dashboard Web (opcional)

Adicionar endpoint de health:

```python
# Em live_bot.py
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        status = {
            'status': 'running',
            'uptime': time.time() - start_time,
            'last_trade': bot.last_trade_time
        }
        self.wfile.write(json.dumps(status).encode())

# Rodar em thread separada
httpd = HTTPServer(('', 8080), HealthHandler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
```

### 3. Uptim Robot (grátis)

1. Acesse https://uptimerobot.com
2. Adicione monitor HTTP
3. URL: `https://seu-app.onrender.com` ou Railway URL
4. Receba alertas se cair

---

## 💰 Custos Estimados

### Railway:
```
Base: $0 (crédito $5/mês)
Uso: ~$0.20/dia
Total: ~$6/mês
```

### Render:
```
Starter: $7/mês
Disk (1GB): $0.25/mês
Total: ~$7.25/mês
```

**Mais barato que um VPS!** 💪

---

## 🚀 Deploy em 5 Minutos (TL;DR)

### Railway (MAIS FÁCIL):
```bash
# 1. Push código
git push origin main

# 2. Ir para railway.app
# 3. New Project → Deploy from GitHub → Selecionar repo
# 4. Adicionar variáveis de ambiente
# 5. Pronto! 🎉
```

### Render:
```bash
# 1. Push código
git push origin main

# 2. Ir para render.com
# 3. New → Web Service → Conectar repo
# 4. Escolher Docker
# 5. Adicionar variáveis
# 6. Create Service
# 7. Pronto! 🎉
```

---

## 📚 Recursos Úteis

- **Render Docs:** https://render.com/docs
- **Railway Docs:** https://docs.railway.app
- **Docker Docs:** https://docs.docker.com

---

## ✅ Checklist Final

Antes de fazer deploy:

- [ ] Push código para GitHub
- [ ] Verificar Dockerfile funciona local
- [ ] Adicionar todas variáveis de ambiente
- [ ] Configurar persistent storage
- [ ] Testar Telegram notifications
- [ ] Configurar monitoring
- [ ] Começar com DRY_RUN=true
- [ ] Monitorar logs por 24h
- [ ] Mudar para DRY_RUN=false quando confiante

---

**Boa sorte! 🚀**

*Se precisar de ajuda, me avise!*
