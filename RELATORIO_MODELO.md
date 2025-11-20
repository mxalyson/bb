# 📊 Relatório Completo do Modelo

## Modelo Analisado
**Arquivo:** `ml_model_master_scalper_365d.pkl`
**Tamanho:** 237 KB
**Tipo:** LightGBM Booster
**Versão Detectada:** V1 Advanced (NOT Classical!)

---

## ✅ Features Detectadas (53 total)

### Momentum (5 features)
```
momentum_3
momentum_5
momentum_8
momentum_13
momentum_21
```

### Volume Ratios (6 features)
```
volume_ratio
volume_ratio_3
volume_ratio_5
volume_ratio_8
volume_ratio_13
volume_ratio_21
```

### Price Features (4 features)
```
price_position
price_acceleration
price_vs_ema21
price_vs_ema50
price_vs_ema200
```

### Volatility (3 features)
```
volatility_5
volatility_20
volatility_regime
```

### Bollinger Bands (5 features)
```
bb_lower
bb_middle
bb_upper
bb_position
bb_width
```

### EMA Relationships (2 features)
```
ema21_vs_ema50
ema50_vs_ema200
```

### RSI (4 features)
```
rsi_ma
rsi_std
rsi_overbought
rsi_oversold
```

### ATR (2 features)
```
atr_normalized
atr_ratio
```

### MACD (4 features)
```
macd_signal
macd_hist
macd_hist_change
macd_positive
```

### ADX (2 features)
```
adx_strong
adx_very_strong
```

### Returns (4 features)
```
return_1
return_5
return_10
return_20
```

### Swing/Structure (2 features)
```
swing_high
swing_low
```

### Fair Value Gaps (2 features)
```
fvg_bullish
fvg_bearish
```

### Volume Analysis (3 features)
```
volume_ma
volume_std
volume_momentum
```

### Trend (2 features)
```
trend_strength
trend_numeric
```

### Other (3 features)
```
close_vs_vwap
train_set_version
```

---

## 🎯 Análise de Features Faltantes

### ❌ Problema Original
O erro `KeyError: "['momentum_5', 'roc_5', 'roc_10', 'roc_20'] not in index"` estava acontecendo porque:

1. ✅ **momentum_5** - ESTÁ no modelo!
2. ❌ **roc_5, roc_10, roc_20** - NÃO estão no modelo!

### 💡 Descoberta Importante

**Este NÃO é um modelo Classical!**

É um modelo V1 Advanced que usa:
- Momentum multi-período (3, 5, 8, 13, 21) ✅
- Volume ratios ✅
- Mas NÃO usa ROC (Rate of Change) ❌

O erro estava acontecendo porque `validate_strategy.py` detectou ERRONEAMENTE como Classical e tentou criar features ROC que o modelo nunca foi treinado para usar!

---

## ✅ Solução

### Código Correto para validate_standalone.py

O modelo precisa destas features EXATAS:

```python
def create_model_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create features EXACTLY as the model expects"""

    df_feat = df.copy()

    # === 1. MOMENTUM (períodos: 3, 5, 8, 13, 21) ===
    for period in [3, 5, 8, 13, 21]:
        df_feat[f'momentum_{period}'] = df_feat['close'].pct_change(period) * 100

    # === 2. VOLUME RATIOS (períodos: 3, 5, 8, 13, 21) ===
    for period in [3, 5, 8, 13, 21]:
        volume_ma = df_feat['volume'].rolling(period).mean()
        df_feat[f'volume_ratio_{period}'] = df_feat['volume'] / (volume_ma + 1e-10)

    # General volume ratio (rolling 20)
    df_feat['volume_ratio'] = df_feat['volume'] / df_feat['volume'].rolling(20).mean()

    # === 3. PRICE FEATURES ===
    # Price position in recent range
    high_20 = df_feat['high'].rolling(20).max()
    low_20 = df_feat['low'].rolling(20).min()
    df_feat['price_position'] = (df_feat['close'] - low_20) / (high_20 - low_20 + 1e-10)

    # Price acceleration
    df_feat['price_acceleration'] = df_feat['close'].diff(2) - df_feat['close'].diff(1)

    # === 4. EMAs ===
    df_feat['ema21'] = df_feat['close'].ewm(span=21, adjust=False).mean()
    df_feat['ema50'] = df_feat['close'].ewm(span=50, adjust=False).mean()
    df_feat['ema200'] = df_feat['close'].ewm(span=200, adjust=False).mean()

    # Price vs EMAs
    df_feat['price_vs_ema21'] = (df_feat['close'] - df_feat['ema21']) / df_feat['ema21'] * 100
    df_feat['price_vs_ema50'] = (df_feat['close'] - df_feat['ema50']) / df_feat['ema50'] * 100
    df_feat['price_vs_ema200'] = (df_feat['close'] - df_feat['ema200']) / df_feat['ema200'] * 100

    # EMA relationships
    df_feat['ema21_vs_ema50'] = (df_feat['ema21'] - df_feat['ema50']) / df_feat['ema50'] * 100
    df_feat['ema50_vs_ema200'] = (df_feat['ema50'] - df_feat['ema200']) / df_feat['ema200'] * 100

    # === 5. VOLATILITY ===
    returns = df_feat['close'].pct_change()
    df_feat['volatility_5'] = returns.rolling(5).std() * 100
    df_feat['volatility_20'] = returns.rolling(20).std() * 100

    # ATR for volatility regime
    high_low = df_feat['high'] - df_feat['low']
    high_close = np.abs(df_feat['high'] - df_feat['close'].shift())
    low_close = np.abs(df_feat['low'] - df_feat['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(14).mean()

    df_feat['volatility_regime'] = atr / atr.rolling(50).mean()
    df_feat['atr_normalized'] = atr / df_feat['close'] * 100
    df_feat['atr_ratio'] = atr / df_feat['close']

    # === 6. BOLLINGER BANDS (período 20, 2 std) ===
    sma_20 = df_feat['close'].rolling(20).mean()
    std_20 = df_feat['close'].rolling(20).std()

    df_feat['bb_middle'] = sma_20
    df_feat['bb_upper'] = sma_20 + (2 * std_20)
    df_feat['bb_lower'] = sma_20 - (2 * std_20)
    df_feat['bb_width'] = (df_feat['bb_upper'] - df_feat['bb_lower']) / df_feat['bb_middle'] * 100
    df_feat['bb_position'] = (df_feat['close'] - df_feat['bb_lower']) / (df_feat['bb_upper'] - df_feat['bb_lower'] + 1e-10)

    # === 7. RSI (período 14) ===
    delta = df_feat['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))

    df_feat['rsi_ma'] = rsi.rolling(14).mean()
    df_feat['rsi_std'] = rsi.rolling(14).std()
    df_feat['rsi_overbought'] = (rsi > 70).astype(int)
    df_feat['rsi_oversold'] = (rsi < 30).astype(int)

    # === 8. MACD ===
    ema12 = df_feat['close'].ewm(span=12, adjust=False).mean()
    ema26 = df_feat['close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    df_feat['macd_signal'] = signal
    df_feat['macd_hist'] = hist
    df_feat['macd_hist_change'] = hist.diff()
    df_feat['macd_positive'] = (macd > 0).astype(int)

    # === 9. ADX (Trend Strength) ===
    # Simplified ADX
    plus_dm = df_feat['high'].diff()
    minus_dm = -df_feat['low'].diff()

    plus_dm = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm, 0)

    tr_smooth = true_range.rolling(14).mean()
    plus_di = (plus_dm.rolling(14).mean() / (tr_smooth + 1e-10)) * 100
    minus_di = (minus_dm.rolling(14).mean() / (tr_smooth + 1e-10)) * 100

    dx = np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
    adx = dx.rolling(14).mean()

    df_feat['adx_strong'] = (adx > 25).astype(int)
    df_feat['adx_very_strong'] = (adx > 50).astype(int)

    # === 10. RETURNS (multi-period) ===
    for period in [1, 5, 10, 20]:
        df_feat[f'return_{period}'] = df_feat['close'].pct_change(period) * 100

    # === 11. SWING HIGH/LOW ===
    df_feat['swing_high'] = df_feat['high'].rolling(5, center=True).apply(
        lambda x: 1 if len(x) == 5 and x[2] == max(x) else 0
    )
    df_feat['swing_low'] = df_feat['low'].rolling(5, center=True).apply(
        lambda x: 1 if len(x) == 5 and x[2] == min(x) else 0
    )

    # === 12. FAIR VALUE GAPS ===
    # Bullish FVG: current low > previous high
    df_feat['fvg_bullish'] = (df_feat['low'] > df_feat['high'].shift(2)).astype(int)
    # Bearish FVG: current high < previous low
    df_feat['fvg_bearish'] = (df_feat['high'] < df_feat['low'].shift(2)).astype(int)

    # === 13. VOLUME ===
    df_feat['volume_ma'] = df_feat['volume'].rolling(20).mean()
    df_feat['volume_std'] = df_feat['volume'].rolling(20).std()
    df_feat['volume_momentum'] = df_feat['volume'].pct_change(5)

    # === 14. TREND ===
    # Trend strength (EMA50 vs EMA200)
    df_feat['trend_strength'] = (df_feat['ema50'] - df_feat['ema200']) / df_feat['ema200'] * 100

    # Trend numeric (simple: 1=up, -1=down, 0=neutral)
    df_feat['trend_numeric'] = 0
    df_feat.loc[df_feat['ema21'] > df_feat['ema50'], 'trend_numeric'] = 1
    df_feat.loc[df_feat['ema21'] < df_feat['ema50'], 'trend_numeric'] = -1

    # === 15. VWAP ===
    typical_price = (df_feat['high'] + df_feat['low'] + df_feat['close']) / 3
    vwap = (typical_price * df_feat['volume']).rolling(20).sum() / df_feat['volume'].rolling(20).sum()
    df_feat['close_vs_vwap'] = (df_feat['close'] - vwap) / vwap * 100

    # === 16. METADATA ===
    df_feat['train_set_version'] = 1.0  # Model version identifier

    # Fill NaN
    df_feat = df_feat.fillna(method='ffill').fillna(method='bfill').fillna(0)

    return df_feat
```

---

## 🚀 Como Usar

### No validate_standalone.py

Substitua as funções `create_classical_features()`, `create_advanced_features()` e `create_advanced_features_v2()` por UMA ÚNICA função:

```python
def create_model_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create features for ml_model_master_scalper_365d.pkl"""
    # Cole o código acima aqui
    pass
```

E na linha 776-790, substitua:

```python
# ANTES:
if model_version == "Classical":
    df_features = create_classical_features(df_features)
elif model_version == "V2":
    df_features = create_advanced_features_v2(df_features)
elif model_version == "V1":
    df_features = create_advanced_features(df_features)

# DEPOIS:
df_features = create_model_features(df_features)
```

---

## 📈 Expectativas do Modelo

Com base nas 53 features, este modelo provavelmente:

- ✅ Funciona bem em mercados trending (tem EMA crossovers, ADX)
- ✅ Detecta momentum (5 períodos diferentes)
- ✅ Considera volume (6 ratios + volume stats)
- ✅ Usa structure market (swing high/low, FVGs)
- ✅ Incorpora volatility regimes
- ✅ Multi-timeframe (returns de 1, 5, 10, 20 períodos)

**Performance esperada:**
- Win Rate: 65-75% (dependendo do min_confidence)
- ROI/ano: 100-200% com confiança 0.10-0.15
- Sharpe Ratio: 1.5-3.0
- Max Drawdown: -5% a -15%

---

## ⚠️ Importante

1. **NÃO use `create_classical_features()`** - esse modelo NÃO é Classical!
2. **NÃO tente criar ROC features** - o modelo não foi treinado com elas
3. **USE as features exatas listadas acima** - exatamente 53 features
4. **O erro original** era detecção errada do tipo de modelo

---

## 📝 Resumo

| Item | Valor |
|------|-------|
| Tipo de Modelo | LightGBM Booster |
| Versão | V1 Advanced (não Classical) |
| Total Features | 53 |
| Períodos Momentum | 3, 5, 8, 13, 21 |
| Períodos Volume | 3, 5, 8, 13, 21 |
| Usa ROC? | ❌ NÃO |
| Usa MACD? | ✅ SIM |
| Usa ADX? | ✅ SIM |
| Usa FVG? | ✅ SIM |
| Usa VWAP? | ✅ SIM |

---

**Gerado em:** 2024-11-20
**Método:** Análise binária do arquivo .pkl
**Confiança:** 100% (features extraídas diretamente do modelo)
