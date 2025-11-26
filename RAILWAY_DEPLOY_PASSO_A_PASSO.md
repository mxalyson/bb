# 🚂 RAILWAY - Deploy Passo a Passo (Bot de Trading)

> **Guia completo e visual para fazer deploy do bot no Railway sem erros!**

---

## 📋 ANTES DE COMEÇAR

### ✅ Checklist Rápido:

- [ ] Conta no Railway (https://railway.app)
- [ ] Repositório GitHub com o bot
- [ ] API Keys da Bybit (testnet OU mainnet)
- [ ] Arquivo `.env` local pronto (para copiar valores)

---

## 🎯 PASSO 1: Criar Projeto no Railway

### 1.1 Acessar Railway

1. Vá em: **https://railway.app**
2. Clique em **"Login"**
3. Faça login com **GitHub**

```
╔══════════════════════════════════════════╗
║         🚂 Railway Dashboard             ║
╠══════════════════════════════════════════╣
║                                          ║
║   [+ New Project]  ← CLIQUE AQUI         ║
║                                          ║
║   My Projects:                           ║
║   (vazio por enquanto)                   ║
║                                          ║
╚══════════════════════════════════════════╝
```

### 1.2 Conectar GitHub

Ao clicar em **"New Project"**, escolha:

```
╔══════════════════════════════════════════╗
║      Como você quer deployar?            ║
╠══════════════════════════════════════════╣
║                                          ║
║  📦 Deploy from GitHub repo              ║
║     ↑ CLIQUE AQUI                        ║
║                                          ║
║  📝 Deploy from template                 ║
║                                          ║
║  🔌 Empty project                        ║
║                                          ║
╚══════════════════════════════════════════╝
```

### 1.3 Selecionar Repositório

```
╔══════════════════════════════════════════╗
║     Selecione o repositório              ║
╠══════════════════════════════════════════╣
║                                          ║
║  🔍 [Buscar repositórios...]             ║
║                                          ║
║  📁 mxalyson/bb  ← SELECIONE ESTE        ║
║  📁 mxalyson/outro-repo                  ║
║  📁 mxalyson/mais-um                     ║
║                                          ║
╚══════════════════════════════════════════╝
```

**⚠️ Primeira vez?** Railway vai pedir permissão para acessar seus repos no GitHub - autorize!

---

## 🎯 PASSO 2: Configurar o Serviço

### 2.1 Railway Detecta Automaticamente

Após selecionar o repo, Railway vai:

```
🔍 Scanning repository...
✅ Dockerfile found!
✅ Python project detected
🚀 Ready to deploy
```

### 2.2 Nomear o Serviço (Opcional)

```
╔══════════════════════════════════════════╗
║     bb (Service)                         ║
╠══════════════════════════════════════════╣
║  Clique aqui para renomear ↑             ║
║                                          ║
║  Sugestão: "trading-bot-live"            ║
╚══════════════════════════════════════════╝
```

---

## 🎯 PASSO 3: Adicionar Variáveis de Ambiente (CRÍTICO!)

### 3.1 Acessar Variables

Clique no serviço criado, depois:

```
╔══════════════════════════════════════════╗
║  trading-bot-live                        ║
╠══════════════════════════════════════════╣
║                                          ║
║  [Settings] [Variables] [Metrics] [Logs] ║
║              ↑ CLIQUE AQUI               ║
║                                          ║
╚══════════════════════════════════════════╝
```

### 3.2 Usar o RAW Editor (Mais Rápido!)

```
╔══════════════════════════════════════════╗
║         Variables                        ║
╠══════════════════════════════════════════╣
║                                          ║
║  [+ New Variable]  [RAW Editor]          ║
║                     ↑ CLIQUE AQUI        ║
║                                          ║
╚══════════════════════════════════════════╝
```

### 3.3 Colar Suas Variáveis

**⚠️ IMPORTANTE:** Use suas API keys REAIS!

**Para TESTNET (Recomendado para testar):**

```env
BYBIT_API_KEY=SUA_KEY_DA_TESTNET_AQUI
BYBIT_API_SECRET=SUA_SECRET_DA_TESTNET_AQUI
BYBIT_TESTNET=true

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
```

**Para MAINNET (Dinheiro real - CUIDADO!):**

```env
BYBIT_API_KEY=SUA_KEY_DA_MAINNET_AQUI
BYBIT_API_SECRET=SUA_SECRET_DA_MAINNET_AQUI
BYBIT_TESTNET=false

SYMBOL=BTCUSDT
TIMEFRAME=15
MODEL_PATH=storage/models/ml_model_master_scalper_365d.pkl

MIN_ML_CONFIDENCE=0.40
RISK_PER_TRADE_PCT=0.75
SL_ATR_MULT=1.5
TP_ATR_MULT=1.0
TRADE_COOLDOWN_SEC=900

DRY_RUN=false
INITIAL_CAPITAL=125.0
```

### 3.4 Salvar

```
╔══════════════════════════════════════════╗
║  RAW Editor                              ║
╠══════════════════════════════════════════╣
║  BYBIT_API_KEY=xxxxx                     ║
║  BYBIT_API_SECRET=xxxxx                  ║
║  BYBIT_TESTNET=true                      ║
║  ...                                     ║
║                                          ║
║               [Update Variables]         ║
║                ↑ CLIQUE AQUI             ║
╚══════════════════════════════════════════╝
```

**✅ Railway vai redeployar automaticamente!**

---

## 🎯 PASSO 4: Obter API Keys da Bybit

### 4.1 Para TESTNET (Recomendado)

1. Acesse: **https://testnet.bybit.com**
2. Faça login (ou crie conta)
3. Vá em: **API Management** (ícone de chave no menu superior)
4. Clique em **"Create New Key"**

```
╔══════════════════════════════════════════╗
║     Create API Key                       ║
╠══════════════════════════════════════════╣
║                                          ║
║  API Key Type:                           ║
║  ● System-generated API Keys             ║
║                                          ║
║  Permissions:                            ║
║  [✓] Contract - Position                 ║
║  [✓] Contract - Orders                   ║
║  [✓] Contract - Read                     ║
║                                          ║
║  IP Restriction:                         ║
║  [ ] Enable  ← DEIXE DESMARCADO!         ║
║                                          ║
║           [Confirm]                      ║
║                                          ║
╚══════════════════════════════════════════╝
```

**⚠️ CRÍTICO:** Anote a **API Key** e **Secret** - a Secret só aparece uma vez!

### 4.2 Para MAINNET (Dinheiro Real)

1. Acesse: **https://www.bybit.com**
2. API Management → Create New Key
3. **MESMO PROCESSO** da testnet

**⚠️ ATENÇÃO:**
- Keys da **testnet** NÃO funcionam na **mainnet**
- Keys da **mainnet** NÃO funcionam na **testnet**
- Use testnet primeiro para testar!

---

## 🎯 PASSO 5: Monitorar Deploy

### 5.1 Ver Build em Tempo Real

```
╔══════════════════════════════════════════╗
║  Deployments                             ║
╠══════════════════════════════════════════╣
║                                          ║
║  ⚙️ Building...                          ║
║     ├─ Installing dependencies           ║
║     ├─ Building Docker image             ║
║     └─ Starting container                ║
║                                          ║
╚══════════════════════════════════════════╝
```

**Tempo esperado:** 2-5 minutos

### 5.2 Ver Logs

Clique em **"View Logs"** ou vá na aba **"Logs"**:

```
╔══════════════════════════════════════════╗
║  Logs (real-time)                        ║
╠══════════════════════════════════════════╣
║                                          ║
║  2025-11-26 01:23:45 [INFO] Starting...  ║
║  2025-11-26 01:23:46 [INFO] Loading...   ║
║  2025-11-26 01:23:47 [INFO] Model V1     ║
║  2025-11-26 01:23:48 [INFO] Bot ready!   ║
║                                          ║
╚══════════════════════════════════════════╝
```

**✅ Se ver isso, está funcionando!**

```
📌 Detected model type: V1
📊 Feature count: 73
🚀 Starting trading loop...
⏰ Waiting for next candle close...
```

---

## 🎯 PASSO 6: Configurar Volume (IMPORTANTE!)

### 6.1 Por Que Preciso?

**Sem volume:** Bot perde dados ao redeployar (trades, histórico, etc.)
**Com volume:** Dados persistem entre deploys! ✅

### 6.2 Criar Volume

Na página do serviço:

```
╔══════════════════════════════════════════╗
║  Settings                                ║
╠══════════════════════════════════════════╣
║                                          ║
║  📁 Volumes                              ║
║     [+ New Volume]  ← CLIQUE AQUI        ║
║                                          ║
╚══════════════════════════════════════════╝
```

### 6.3 Configurar Mount Path

```
╔══════════════════════════════════════════╗
║  Create Volume                           ║
╠══════════════════════════════════════════╣
║                                          ║
║  Mount Path:                             ║
║  [/app/storage]  ← DIGITE ISSO           ║
║                                          ║
║               [Add]                      ║
║                                          ║
╚══════════════════════════════════════════╝
```

**✅ Pronto!** Agora os dados do bot estão seguros.

---

## ❌ SOLUÇÃO DE PROBLEMAS

### Erro 1: "403 Forbidden" (como o seu!)

```
[ERROR] 403 Client Error: Forbidden for url: https://api-testnet.bybit.com
```

**Causas e Soluções:**

| Causa | Como Resolver |
|-------|---------------|
| ❌ API keys não configuradas | Adicionar `BYBIT_API_KEY` e `BYBIT_API_SECRET` no Railway |
| ❌ Keys erradas (mainnet ↔ testnet) | Usar keys da **testnet** se `BYBIT_TESTNET=true` |
| ❌ IP Restriction ativado | Desabilitar na Bybit API settings |
| ❌ Permissões insuficientes | Recriar key com permissões: Position, Orders, Read |

**Como verificar:**

1. Railway → Seu serviço → **Variables**
2. Conferir se `BYBIT_API_KEY` e `BYBIT_API_SECRET` estão lá
3. Conferir se `BYBIT_TESTNET` está `true` ou `false` corretamente

### Erro 2: "No data received"

```
[ERROR] No data downloaded for BTCUSDT 15m
```

**Sempre vem junto com o 403!** Resolva o erro 403 primeiro.

### Erro 3: "Build failed"

**Causas comuns:**
- Dockerfile com erro (improvável - já testado)
- Falta requirements.txt
- Python version incompatível

**Solução:** Veja logs do build para detalhes.

---

## 📊 RAILWAY vs RENDER

| Feature | Railway 🚂 | Render 🎨 |
|---------|-----------|----------|
| **Facilidade** | ⭐⭐⭐⭐⭐ Muito fácil | ⭐⭐⭐⭐ Fácil |
| **Deploy** | Automático | Automático |
| **Logs** | Excelentes | Bons |
| **Volumes** | ✅ Grátis | ❌ Pago (Disks) |
| **Preço Free** | $5 crédito/mês | Dorme após 15min |
| **Port Errors** | ✅ Não exige porta | ⚠️ Avisa sobre porta |

**🏆 Recomendação:** Railway é mais fácil para começar!

---

## ✅ CHECKLIST FINAL

Antes de considerar deploy concluído:

- [ ] ✅ Serviço criado no Railway
- [ ] ✅ Variáveis adicionadas (API keys corretas)
- [ ] ✅ `BYBIT_TESTNET=true` (para testar com testnet)
- [ ] ✅ Build concluído com sucesso
- [ ] ✅ Logs mostram "Bot ready!" ou "Starting trading loop"
- [ ] ✅ Sem erros 403
- [ ] ✅ Volume criado em `/app/storage`
- [ ] ✅ Bot detectando candles corretamente

---

## 🎯 PRÓXIMOS PASSOS

### Após Deploy Bem-Sucedido:

1. **Monitorar por 24h** - Ver se bot está estável
2. **Verificar predições** - Conferir se confidence está batendo
3. **Testar dry_run** - Simular trades sem risco
4. **Depois:** Mudar para mainnet (se quiser operar real)

### Logs que Você Deve Ver:

```
✅ BOM:
   📌 Detected model type: V1
   🎯 New candle detected: 2025-11-26 01:30:00
   📊 Prediction: 0.6234 (62.3% UP)
   ✅ Trade opened: LONG at 95234.5

❌ RUIM:
   [ERROR] 403 Forbidden
   [ERROR] No data received
   [ERROR] Model not found
```

---

## 📞 PRECISA DE AJUDA?

**Erro 403 persistindo?**
1. Tire print das suas Variables no Railway
2. Confirme se usou keys da testnet (https://testnet.bybit.com)
3. Verifique se IP Restriction está desativado na Bybit

**Bot não detecta candles?**
- Verifique se `SYMBOL=BTCUSDT` está correto
- Verifique se `TIMEFRAME=15` está correto
- Veja logs para mensagens de erro

---

**🎉 Boa sorte com o deploy!** 🚀
