# 🚀 Como Rodar o Backtest

## ✅ Status: PRONTO PARA USAR!

A estrutura do projeto foi organizada e o backtest está pronto para rodar.

---

## 📁 Estrutura Organizada

```
bb/
├── core/                    # Módulos principais
│   ├── __init__.py
│   ├── utils.py            # Configuração e logging
│   ├── bybit_rest.py       # Cliente REST Bybit
│   ├── data.py             # Download de dados
│   ├── features.py         # Feature engineering
│   └── risk.py             # Gestão de risco
├── storage/
│   └── models/
│       └── ml_model_master_scalper_365d.pkl
├── 1.py                    # ⭐ Script de backtest completo
├── live_bot.py             # Bot de trading ao vivo
├── .env                    # Configurações (edite com suas API keys)
└── .env.example            # Modelo de configuração
```

---

## 🔧 Instalação (Uma Vez)

Antes de rodar pela primeira vez, instale as dependências:

```bash
pip install pandas numpy scikit-learn scipy pybit python-dotenv
```

---

## 🎯 Como Rodar o Backtest

### Opção 1: Backtest Completo com Testes ATR (RECOMENDADO)

```bash
python 1.py --symbol BTCUSDT --days 180 --fee-type taker
```

**O que testa:**
- ✅ 19 níveis de confiança (0% até 90%)
- ✅ Análise por faixas de confiança (0-20%, 20-30%, etc.)
- ✅ 6 combinações de ATR multipliers:
  - SL: 2.0x e 1.5x
  - TP: 1.0x, 0.8x, 0.7x
- ✅ Estatísticas completas: WR, ROI, Sharpe, Max DD, Profit Factor
- ✅ Recomendações para .env

**Parâmetros:**
- `--symbol BTCUSDT`: Par para testar (padrão: BTCUSDT)
- `--days 180`: Período histórico (padrão: 180 dias)
- `--fee-type taker`: Tipo de taxa (taker=0.055%, maker=0.02%)
- `--verbose-trades`: Mostrar cada trade individual (OPCIONAL)

### Opção 2: Ver Cada Trade (Modo Debug)

```bash
python 1.py --symbol BTCUSDT --days 90 --verbose-trades --fee-type taker
```

Mostra logs detalhados:
```
🟢 ENTRY #123: LONG @ $85,450.00
   Confidence: 45.2% | Size: $750.00 | Capital: $10,000.00
   SL: $84,200.00 (-1.46%) | TP: $86,700.00 (+1.46%)

✅ EXIT 🟢 LONG: 🎯 TP
   Entry: $85,450.00 → Exit: $86,700.00
   PnL: +1.35% ($10.12) | Fees: $0.83
   Duration: 2025-01-15 10:00:00 → 2025-01-15 14:30:00
```

### Opção 3: Testar com Maker Fees (Limit Orders)

```bash
python 1.py --symbol BTCUSDT --days 180 --fee-type maker
```

Simula uso de limit orders (0.02% fee) ao invés de market orders (0.055%).

---

## 📊 Exemplo de Output

```
================================================================================
🔬 VALIDAÇÃO COMPLETA DA ESTRATÉGIA
================================================================================
Symbol: BTCUSDT
Period: 180 days
Model: ml_model_master_scalper_365d.pkl

📥 Downloading data...
✅ Downloaded 17,280 candles

🔨 Building features...
📌 Detected model type: Classical
✅ Features ready: 87 columns

🎯 Using threshold: 0.500

================================================================================
📊 TESTE DE SENSIBILIDADE - MIN_ML_CONFIDENCE
================================================================================

Confiança | Trades |  WR   |   ROI   | Sharpe | MaxDD |  PF  | Avg Conf
----------|--------|-------|---------|--------|-------|------|----------
  0.00    |   856  | 78.3% | +124.67%|  8.42  | -8.3% | 4.23 |  32.1%
  0.25    |   324  | 89.2% | +67.89% | 11.34  | -3.2% | 8.91 |  42.3%
  0.40    |   156  | 94.9% | +42.12% | 13.67  | -1.8% | 17.2 |  51.2%

🏆 MELHOR CONFIGURAÇÃO (por ROI):
   MIN_CONFIDENCE: 0.25
   Win Rate: 89.2%
   ROI: +67.89%
   Sharpe: 11.34

================================================================================
🎯 TESTANDO DIFERENTES ATR MULTIPLIERS
================================================================================

ATR Config               | Trades |  WR   |   ROI   | Sharpe | MaxDD | PF
-------------------------|--------|-------|---------|--------|-------|------
2.0x SL, 1.0x TP (padrão)| 194    | 92.8% | +36.62% | 10.33  | -2.4% | 4.59
2.0x SL, 0.8x TP         | 213    | 89.7% | +23.64% |  7.64  | -2.2% | 3.24
2.0x SL, 0.7x TP         | 225    | 89.8% | +20.66% |  7.35  | -2.2% | 3.45
1.5x SL, 1.0x TP         | 194    | 90.2% | +28.91% |  9.12  | -3.1% | 3.87
1.5x SL, 0.8x TP         | 213    | 87.8% | +18.45% |  6.89  | -2.8% | 2.98
1.5x SL, 0.7x TP         | 225    | 88.0% | +16.23% |  6.56  | -2.6% | 3.12

🏆 MELHOR CONFIGURAÇÃO ATR (por ROI):
   2.0x SL, 1.0x TP (padrão)
   ROI: +36.62%
   Win Rate: 92.8%
   Sharpe: 10.33

💾 Adicione no seu .env:
   MIN_ML_CONFIDENCE=0.25
   SL_ATR_MULT=2.0
   TP_ATR_MULT=1.0
```

---

## 🔍 Como Saber se o Backtest Está Funcionando

Um backtest válido deve:

### 1. ✅ Baixar Dados Reais da Bybit
```
📥 Downloading data...
✅ Downloaded 17,280 candles
```
Se falhar aqui, verifique:
- Conexão com internet
- API keys no .env (se usando testnet=false)

### 2. ✅ Detectar Tipo de Modelo Corretamente
```
📌 Detected model type: Classical
   Required features: 87
```
Significa que o modelo foi carregado e features detectadas.

### 3. ✅ Simular Trades Realistas
Cada trade deve:
- Entry baseado em sinal ML (acima do threshold)
- SL/TP calculados com ATR
- Verificar se high/low tocou SL/TP
- Descontar taxas (0.055% x 2 = 0.11%)

### 4. ✅ Reportar Estatísticas Completas
- **Trades**: Número total de operações
- **WR** (Win Rate): % de trades vencedores
- **ROI**: Retorno total sobre investimento inicial
- **Sharpe**: Risco-ajustado (>2 é bom, >3 é excelente)
- **Max DD**: Maior queda do capital
- **PF** (Profit Factor): Lucro/Prejuízo (>2 é bom)

### 5. ✅ Modo Verbose (--verbose-trades)
Se ativar `--verbose-trades`, deve mostrar:
- Entry de cada trade com preço, confiança, size
- Exit com razão (SL/TP/time), PnL líquido, fees
- Duration do trade

---

## 🎯 Lógica do Backtest (Como Funciona)

### Entrada (LONG)
1. Modelo prevê sinal BUY
2. Confiança >= MIN_ML_CONFIDENCE
3. Calcula ATR(14)
4. Define SL = preço - (ATR × 2.0)
5. Define TP = preço + (ATR × 1.0)
6. Size = RISK_PER_TRADE / distância_SL

### Entrada (SHORT)
1. Modelo prevê sinal SELL
2. Confiança >= MIN_ML_CONFIDENCE
3. SL = preço + (ATR × 2.0)
4. TP = preço - (ATR × 1.0)

### Saída
- **Take Profit**: High/Low toca TP → exit em TP
- **Stop Loss**: High/Low toca SL → exit em SL
- **Time Exit**: 48h (192 candles de 15m) → exit em close

### PnL Calculation
```python
# LONG
pnl_pct = ((exit_price - entry_price) / entry_price) * 100

# SHORT
pnl_pct = ((entry_price - exit_price) / entry_price) * 100

# Fees (entrada + saída)
fees = size * 0.00055 * 2

# PnL líquido
pnl_net = pnl_amount - fees
```

---

## 🐛 Troubleshooting

### ❌ "ModuleNotFoundError: No module named 'pandas'"
```bash
pip install pandas numpy scikit-learn scipy pybit python-dotenv
```

### ❌ "FileNotFoundError: storage/models/..."
```bash
# Verifique se o modelo está no lugar certo
ls storage/models/ml_model_master_scalper_365d.pkl
```

### ❌ "KeyError: 'bybit_api_key'"
Edite o `.env` e adicione suas API keys:
```bash
BYBIT_API_KEY=sua_api_key_aqui
BYBIT_API_SECRET=sua_api_secret_aqui
BYBIT_TESTNET=true  # ou false para mainnet
```

### ❌ Download falha (403, timeout)
1. Use VPN se bloqueado geograficamente
2. Ou use `validate_standalone.py` que tem retry logic

---

## 📊 Interpretando os Resultados

### Win Rate (WR)
- **< 50%**: Estratégia ruim
- **50-70%**: OK
- **70-85%**: Bom
- **> 85%**: Excelente (ou overfitting, cuidado!)

### ROI
- Retorno total sobre capital inicial
- Considere o período: +50% em 180 dias = +100% anualizado

### Sharpe Ratio
- Mede retorno ajustado por risco
- **< 1**: Ruim
- **1-2**: OK
- **2-3**: Bom
- **> 3**: Excelente

### Max Drawdown
- Maior queda do capital
- **< 5%**: Conservador
- **5-10%**: Moderado
- **> 10%**: Agressivo

### Profit Factor
- Lucro total / Prejuízo total
- **< 1.5**: Ruim
- **1.5-2**: OK
- **2-3**: Bom
- **> 3**: Excelente

---

## 💡 Dicas

1. **Teste com diferentes períodos:**
   ```bash
   python 1.py --days 90   # 3 meses
   python 1.py --days 180  # 6 meses
   python 1.py --days 365  # 1 ano
   ```

2. **Compare maker vs taker:**
   ```bash
   python 1.py --fee-type maker  # Limit orders (0.02%)
   python 1.py --fee-type taker  # Market orders (0.055%)
   ```

3. **Analise por confidence:**
   O backtest mostra performance por faixas:
   - 0-20%: Sinais fracos
   - 20-30%: Médio-baixo
   - 30-40%: Médio
   - 40-50%: Médio-alto
   - 50-60%: Alto
   - 60-70%: Muito alto
   - 70-80%: Ultra-alto
   - 80-90%: Extremo
   - 90-100%: Certeza absoluta (raro)

4. **TP menor = mais trades:**
   - TP 0.7x: Fecha mais rápido → mais trades → menor WR
   - TP 1.0x: Fecha mais devagar → menos trades → maior WR
   - Trade-off: velocidade vs qualidade

---

## 🎯 Próximos Passos

Após rodar o backtest e encontrar boas configurações:

1. **Atualize o .env:**
   ```bash
   MIN_ML_CONFIDENCE=0.40  # Baseado nos resultados
   SL_ATR_MULT=2.0
   TP_ATR_MULT=1.0
   TRADE_COOLDOWN_SEC=1800
   ```

2. **Teste em paper trading:**
   ```bash
   python live_bot.py  # Com DRY_RUN=true no .env
   ```

3. **Monitore por alguns dias**

4. **Se tudo OK, ative live trading:**
   ```bash
   # No .env:
   DRY_RUN=false
   ```

---

## 📚 Arquivos Relacionados

- `test_backtest.py` - Script de diagnóstico
- `.env.example` - Configurações recomendadas
- `GUIA_COMPLETO_VALIDACAO.md` - Guia detalhado
- `live_bot.py` - Bot de trading ao vivo

---

**Boa sorte! 🚀**
