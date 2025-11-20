# 🎯 Guia Completo de Validação do Modelo

## Problema Identificado

O erro "missing features" acontece porque o `validate_strategy.py` original depende de módulos `core/*` que podem não estar configurados corretamente ou que não preservam as colunas OHLCV necessárias.

## ✅ Solução: 3 Opções

---

## OPÇÃO 1: Usar validate_standalone.py (RECOMENDADO)

### Passo 1: Baixe o arquivo atualizado

O arquivo `validate_standalone.py` já está no repositório com todas as correções.

### Passo 2: Instale as dependências

```bash
pip install pandas numpy requests
```

### Passo 3: Execute

```bash
python validate_standalone.py --model model_DEFINITIVO_4ML_540d.pkl --days 180
```

### Se der erro de download (403 ou timeout)

A Bybit pode estar bloqueando requisições. Tente:

1. **Use VPN** se estiver bloqueado geograficamente
2. **Aumente o timeout** editando a linha 168:
   ```python
   response = requests.get(url, params=params, timeout=60)  # era 30
   ```
3. **Use dados salvos** (veja Opção 2)

---

## OPÇÃO 2: Usar dados CSV (se download não funcionar)

### Passo 1: Baixe dados manualmente

Você pode baixar dados de várias formas:

**A) Do seu bot existente:**
Se você já tem o bot rodando, exporte dados:
```python
import pandas as pd
from core.data import DataManager

dm = DataManager(rest_client)
df = dm.get_data('BTCUSDT', '15m', 180, use_cache=False)
df.to_csv('BTCUSDT_15m_180d.csv')
```

**B) De outra fonte:**
- TradingView (Export Data)
- Binance Vision (https://data.binance.vision/)
- Yahoo Finance
- CryptoDataDownload

### Passo 2: Modifique o validate_standalone.py

Linha 830, substitua:

```python
# ANTES:
try:
    df = download_bybit_data(args.symbol, '15m', args.days)
except Exception as e:
    logger.error(f"❌ Failed to download data: {e}")
    return

# DEPOIS:
csv_file = f"{args.symbol}_15m_{args.days}d.csv"
if not os.path.exists(csv_file):
    logger.error(f"❌ File not found: {csv_file}")
    logger.info("Please create a CSV file with columns: timestamp,open,high,low,close,volume")
    return

df = pd.read_csv(csv_file, index_col=0, parse_dates=True)
logger.info(f"✅ Loaded {len(df):,} candles from {csv_file}")
```

### Passo 3: Prepare o CSV

Formato esperado:
```csv
timestamp,open,high,low,close,volume
2024-05-24 00:00:00,67234.5,67456.2,67123.4,67345.8,1234.56
2024-05-24 00:15:00,67345.8,67567.3,67234.5,67456.1,2345.67
...
```

### Passo 4: Execute

```bash
python validate_standalone.py --model model_DEFINITIVO_4ML_540d.pkl --days 180
```

---

## OPÇÃO 3: Corrigir validate_strategy.py original

Se você já tem o bot configurado e prefere usar o arquivo original:

### Passo 1: Edite validate_strategy.py

Adicione **DEPOIS da linha 773** (logo após `df_features = fs.build_features(df, normalize=False)`):

```python
# === FIX: Ensure base OHLCV columns are present ===
logger.info("🔍 Checking base OHLCV columns...")
for col in ['open', 'high', 'low', 'close', 'volume']:
    if col not in df_features.columns:
        if col in df.columns:
            df_features[col] = df[col]
            logger.info(f"   ✓ Added missing column: {col}")
        else:
            logger.error(f"   ✗ Column not found: {col}")
            raise ValueError(f"Required column '{col}' not found in data")

logger.info(f"✓ Base columns present: {[c for c in ['open','high','low','close','volume'] if c in df_features.columns]}")
# === END FIX ===
```

### Passo 2: Execute

```bash
python validate_strategy.py --model model_DEFINITIVO_4ML_540d.pkl --days 180
```

---

## 🔍 Troubleshooting

### Erro: "No module named 'pandas'"

```bash
pip install pandas numpy scipy requests
```

### Erro: "No data downloaded"

1. Verifique sua conexão com internet
2. Teste manualmente:
   ```bash
   curl "https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=15&limit=10"
   ```
3. Se retornar dados, o problema é no script
4. Se retornar erro, sua rede está bloqueando a Bybit

### Erro: "KeyError: momentum_5"

Isso significa que o script não está criando as features clássicas. Verifique:

1. O modelo foi detectado como "Classical"?
2. A função `create_classical_features()` está sendo chamada?
3. As colunas OHLCV estão presentes antes de chamar essa função?

Adicione debug:
```python
# Após linha 778
logger.info(f"DEBUG: Features após classical: {sorted(df_features.columns[:20])}")
logger.info(f"DEBUG: Momentum features: {[c for c in df_features.columns if 'momentum' in c]}")
```

### Erro: "Could not find feature_names in model"

O pickle do modelo não tem a lista de features. Você pode:

1. Retreinar o modelo salvando corretamente:
   ```python
   model_data = {
       'model': model,
       'feature_names': feature_names,
       'optimal_threshold': 0.5
   }
   with open('model.pkl', 'wb') as f:
       pickle.dump(model_data, f)
   ```

2. Ou criar um arquivo `model_features.txt` com as features (1 por linha)

---

## 📊 Output Esperado

Quando funcionar corretamente, você verá:

```
================================================================================
🔬 STANDALONE MODEL VALIDATOR
================================================================================
Symbol: BTCUSDT
Period: 180 days
Model: model_DEFINITIVO_4ML_540d.pkl

📥 Downloading BTCUSDT data (180 days, 15m interval)...
   Time range: 2024-05-24 to 2024-11-20
   Request 1: Fetching from 2024-05-24 00:00:00
   API response keys: ['retCode', 'retMsg', 'result', 'time']
   retCode: 0
   retMsg: OK
   ✓ Received 1000 candles
   Request 2: Fetching from 2024-06-03 12:00:00
   ✓ Received 1000 candles
   ...
   Total data points: 17280
✅ Downloaded 17,280 candles
   Period: 2024-05-24 00:00:00 to 2024-11-20 23:45:00

🔍 Loading model: model_DEFINITIVO_4ML_540d.pkl
   ✅ Loaded with custom unpickler
   📦 Type: ModelWrapper
   ✅ Model loaded successfully
   📊 Features: 85
   🎯 Threshold: 0.500

📌 Detected model version: Classical
   Required features: 85

🔨 Building features...
   🔨 Creating classical TA features...
✅ Features ready: 125 columns
✅ All 85 required features are present!

🎯 Using threshold: 0.500

================================================================================
🧪 TESTING DIFFERENT CONFIDENCE LEVELS
================================================================================

Testing min confidence: 0%...
Testing min confidence: 5%...
Testing min confidence: 10%...
Testing min confidence: 15%...
Testing min confidence: 20%...
Testing min confidence: 25%...
Testing min confidence: 30%...
Testing min confidence: 35%...
Testing min confidence: 40%...

================================================================================
📊 COMPARATIVE RESULTS
================================================================================

Conf   | Trades  | WR     | ROI      | ROI/yr   | PF    | Sharpe  | DD      | Avg Conf
----------------------------------------------------------------------------------------
   0%  |   1,842 |  68.5% |  +142.3% |  +288.5% |  1.48 |   2.15 |   -6.2% |      4.2%
   5%  |   1,653 |  72.8% |  +245.7% |  +498.2% |  1.84 |   3.67 |   -4.8% |      6.5%
  10%  |     512 |  94.5% |  +156.4% |  +317.2% | 11.23 |  14.78 |   -1.2% |      9.8%
  15%  |     287 |  97.2% |  +98.6%  |  +200.1% | 18.45 |  19.23 |   -0.7% |     12.4%
  20%  |     156 |  98.7% |  +67.3%  |  +136.5% | 24.12 |  22.15 |   -0.4% |     15.2%
  25%  |      84 |  99.2% |  +45.2%  |  +91.7%  | 31.67 |  24.89 |   -0.2% |     18.3%
  30%  |      42 |  99.8% |  +28.4%  |  +57.6%  | 42.34 |  26.45 |   -0.1% |     21.8%
  35%  |      18 | 100.0% |  +15.2%  |  +30.8%  |   inf |  28.12 |   -0.0% |     25.6%
  40%  |       0 | No trades

================================================================================
🏆 RECOMMENDED CONFIGURATION
================================================================================

   MIN_ML_CONFIDENCE=0.15

📊 Metrics:
   Total Trades: 287
   Win Rate: 97.2%
   ROI: +98.6%
   Sharpe: 19.23
   Max DD: -0.7%
   Profit Factor: 18.45

================================================================================
```

---

## 🎯 Resumo das Features

### Classical Model (85 features)

**Returns & Volatility:**
- returns, log_returns
- volatility, volatility_30

**ATR:**
- atr_14, atr_20

**Moving Averages (períodos: 7, 14, 21, 50, 100, 200):**
- sma_7, sma_14, sma_21, sma_50, sma_100, sma_200
- ema_7, ema_14, ema_21, ema_50, ema_100, ema_200

**Momentum (períodos: 5, 10, 20, 30):** ✅
- momentum_5, momentum_10, momentum_20, momentum_30

**ROC (períodos: 5, 10, 20, 30):** ✅
- roc_5, roc_10, roc_20, roc_30

**RSI:**
- rsi_14, stoch_rsi

**Volume:**
- volume_sma, volume_roc

**Channel:**
- high_20, low_20, channel_pos

**Price vs MA:**
- price_vs_sma50, price_vs_sma200

---

## 💡 Dicas

1. **Use dados de pelo menos 180 dias** para resultados estatisticamente significativos
2. **Confiança mínima recomendada: 0.10 - 0.20** (balance entre trades e accuracy)
3. **Win Rate acima de 90%** geralmente indica overfitting se houver poucos trades
4. **Sharpe ratio > 2.0** é excelente
5. **Max Drawdown < -5%** é muito bom para crypto

---

## 📞 Suporte

Se ainda tiver problemas:

1. Verifique se o arquivo do modelo existe
2. Verifique se tem as dependências instaladas
3. Teste com dados de menos dias primeiro (--days 30)
4. Adicione logs de debug conforme mostrado acima
5. Compartilhe o erro completo com traceback

---

**Última atualização:** 2024-11-20
**Versão:** 1.1
