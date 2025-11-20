# 🔧 Validador Universal de Modelos

O `validate_strategy.py` agora funciona com **QUALQUER modelo .pkl** independente de como foi salvo!

---

## ✨ Novos Recursos

### 🎯 Carregamento Universal

O script agora detecta automaticamente o formato do modelo:

| Formato | Suportado | Descrição |
|---------|-----------|-----------|
| **Dict padrão** | ✅ | `{'model': ..., 'feature_names': ...}` |
| **ModelWrapper** | ✅ | Objetos com classe customizada |
| **Direct model** | ✅ | LightGBM/sklearn direto |
| **Custom classes** | ✅ | Qualquer classe customizada |

---

## 🚀 Como Usar

### Sintaxe básica

```bash
python validate_strategy.py --model SEU_MODELO.pkl --days DIAS
```

### Exemplos

#### 1. Modelo V1 (padrão)
```bash
python validate_strategy.py --model ml_model_master_scalper_365d.pkl --days 180
```

#### 2. Modelo V2 (com features avançadas)
```bash
python validate_strategy.py --model ml_model_master_scalper_v2_365d.pkl --days 180
```

#### 3. Modelo customizado (com ModelWrapper)
```bash
python validate_strategy.py --model model_DEFINITIVO_4ML_540d.pkl --days 30
```

#### 4. Qualquer outro modelo
```bash
python validate_strategy.py --model meu_modelo_qualquer.pkl --days 90
```

---

## 📊 Output Esperado

### Carregamento do Modelo

```
🔍 Loading model: storage/models/model_DEFINITIVO_4ML_540d.pkl
   ✅ Loaded with custom unpickler
   📦 Object format - type: ModelWrapper
   ✅ Model loaded successfully
   📊 Features: 85
   🎯 Threshold: 0.500

📌 Detected model version: V1
   Required features: 85
```

### Resultados do Backtest

```
================================================================================
📊 RESULTADOS COMPARATIVOS
================================================================================

Conf   | Trades  | WR     | ROI      | ROI/yr   | PF    | Sharpe  | DD      | Avg Conf
----------------------------------------------------------------------------------------
   0%  |   1,538 |  70.2% |  +156.3% |  +317.0% |  1.52 |   2.48 |   -5.6% |      5.8%
   5%  |   1,486 |  74.8% |  +283.4% |  +574.7% |  1.91 |   4.22 |   -4.5% |      7.2%
  10%  |     430 |  96.3% |  +165.2% |  +335.0% | 13.75 |  16.42 |   -1.0% |     10.7%
```

---

## 🔍 Detecção Automática de Versão

O script detecta automaticamente se é modelo **V1** ou **V2**:

### Modelo V1
- Features básicas (~80 features)
- Usa `create_advanced_features()`

### Modelo V2
- Features avançadas (~120 features)
- Usa `create_advanced_features_v2()`
- Includes: RSI multi-period, ROC, Bollinger Bands, higher-order moments

**Detecção**: Verifica se possui features V2 específicas:
- `returns_kurt_50`, `returns_skew_50`
- `rsi_5`, `roc_20`, `bb_width_50`
- `price_position_10`, `price_position_20`, `price_position_50`

---

## 🛠️ Troubleshooting

### ❌ Erro: "Can't get attribute 'ModelWrapper'"

**Antes** (erro):
```python
AttributeError: Can't get attribute 'ModelWrapper' on <module '__main__'>
```

**Agora** (funciona):
```
✅ Loaded with custom unpickler
📦 Object format - type: ModelWrapper
✅ Model loaded successfully
```

**Solução**: O script agora define `ModelWrapper` genérico e usa `UniversalUnpickler`.

---

### ❌ Erro: "Could not find feature_names"

**O script tenta extrair feature_names de várias formas:**

1. Do dict: `data['feature_names']` ou `data['features']`
2. Do objeto: `data.feature_names` ou `data.features`
3. Do modelo: `model.feature_name_()` (LightGBM)
4. Do modelo: `model.feature_names_in_` (sklearn)

Se ainda falhar, significa que o modelo não contém essa informação.

**Solução**: Re-salve o modelo incluindo `feature_names`:

```python
import pickle

model_data = {
    'model': seu_modelo,
    'feature_names': lista_de_features,
    'optimal_threshold': 0.5  # opcional
}

with open('modelo.pkl', 'wb') as f:
    pickle.dump(model_data, f)
```

---

### ❌ Erro: Features faltando no backtest

```
KeyError: "['returns_kurt_50', 'rsi_5', ...] not in index"
```

**Causa**: Modelo V2 precisa de features avançadas, mas foi detectado como V1.

**Solução**: O script agora detecta automaticamente. Se ainda falhar:

1. Verifique quais features o modelo precisa:
```python
import pickle
with open('modelo.pkl', 'rb') as f:
    data = pickle.load(f)
print(data['feature_names'])
```

2. Certifique-se que essas features estão sendo criadas em:
   - `create_advanced_features()` (V1)
   - `create_advanced_features_v2()` (V2)

---

## 📝 Formatos de Modelo Suportados

### Formato 1: Dict padrão (recomendado)

```python
model_data = {
    'model': lgb_model,
    'feature_names': ['close', 'volume', 'rsi', ...],
    'optimal_threshold': 0.52,  # opcional
    'train_accuracy': 0.61,      # opcional
    'val_accuracy': 0.58,        # opcional
    # ... outros metadados
}

pickle.dump(model_data, f)
```

### Formato 2: ModelWrapper

```python
class ModelWrapper:
    def __init__(self, model, feature_names):
        self.model = model
        self.feature_names = feature_names

wrapper = ModelWrapper(lgb_model, ['close', 'volume', ...])
pickle.dump(wrapper, f)
```

### Formato 3: Direto (não recomendado)

```python
# Apenas o modelo, sem metadados
pickle.dump(lgb_model, f)
```

**⚠️ Aviso**: Formato 3 não funciona se `feature_names` não estiver no modelo!

---

## 🎯 Parâmetros de Linha de Comando

| Parâmetro | Descrição | Padrão |
|-----------|-----------|--------|
| `--model` | Nome do arquivo .pkl | `ml_model_master_scalper_365d.pkl` |
| `--symbol` | Par de trading | `BTCUSDT` |
| `--days` | Dias de backtest | `180` |

### Exemplos Avançados

#### Testar em período curto (30 dias)
```bash
python validate_strategy.py --model modelo.pkl --days 30
```

#### Testar em período longo (1 ano)
```bash
python validate_strategy.py --model modelo.pkl --days 365
```

#### Testar outro símbolo (futuro)
```bash
python validate_strategy.py --model modelo.pkl --symbol ETHUSDT --days 180
```

---

## 🔬 Métricas Explicadas

### Win Rate (WR)
- **Bom**: 54-57%
- **Ótimo**: 57-60%
- **Excepcional**: >60%

⚠️ **Cuidado**: WR >90% geralmente indica overfitting ou viés!

### ROI (Return on Investment)
- **Anualizado**: ROI × (365 / dias testados)
- **Bom**: 50-100% ao ano
- **Ótimo**: 100-200% ao ano

### Sharpe Ratio
- **Mede**: Retorno ajustado ao risco
- **Bom**: 1.5-2.5
- **Ótimo**: 2.5-4
- **Impossível**: >10 (provavelmente erro!)

### Profit Factor (PF)
- **Fórmula**: Total ganho / Total perdido
- **Bom**: 1.5-2.5
- **Ótimo**: 2.5-4

### Max Drawdown (DD)
- **Bom**: 5-10%
- **Ótimo**: <5%
- **Ruim**: >20%

---

## ⚠️ Sinais de Alerta

### 🚨 Modelo Provavelmente Enviesado

Se você vê:
```
Win Rate: 96.3%
Sharpe: 16.42
```

**Verifique**:
1. Distribuição de trades: Long vs Short
2. Teste em diferentes períodos (alta, baixa, lateral)
3. Accuracy no treinamento: UP vs DOWN

**Exemplo de modelo enviesado**:
```
UP accuracy:   21.5%  ⚠️  (só erra UPs)
DOWN accuracy: 91.6%  ✅  (sempre acerta DOWNs)
Prediction:    85% DOWN
```

**Problema**: Funciona só em mercado de queda!

---

## 🎓 Casos de Uso

### 1. Comparar Modelos

```bash
# Testar vários modelos no mesmo período
python validate_strategy.py --model modelo_v1.pkl --days 180
python validate_strategy.py --model modelo_v2.pkl --days 180
python validate_strategy.py --model modelo_definitivo.pkl --days 180

# Compare métricas e escolha o melhor
```

### 2. Validar Robustez

```bash
# Testar em diferentes períodos
python validate_strategy.py --model modelo.pkl --days 30   # Último mês
python validate_strategy.py --model modelo.pkl --days 90   # Último trimestre
python validate_strategy.py --model modelo.pkl --days 180  # Último semestre
python validate_strategy.py --model modelo.pkl --days 365  # Último ano

# Modelo robusto: performance similar em todos os períodos
```

### 3. Encontrar Melhor Confidence

O script testa automaticamente:
- 0%, 5%, 10%, 15%, 20%, 25%, 30%, 35%, 40%

**Output final recomenda o melhor**:
```
🏆 Configuração Recomendada:
   MIN_ML_CONFIDENCE=0.10

📊 Métricas:
   Total Trades: 430
   Win Rate: 96.3%
   ROI: +165.20%
```

Use essa configuração no seu `.env`!

---

## 💡 Dicas Finais

### ✅ Boas Práticas

1. **Sempre teste em múltiplos períodos**
   - Mercado de alta
   - Mercado de baixa
   - Mercado lateral

2. **Desconfie de resultados perfeitos**
   - WR >90% geralmente é suspeito
   - Sharpe >10 é impossível
   - DD <1% é muito improvável

3. **Valide estatisticamente**
   - Mínimo 50 trades para ser significativo
   - Mínimo 100 trades para ser confiável

4. **Monitore o viés**
   - Long WR ≈ Short WR (diferença <10%)
   - Quantidade de longs ≈ shorts

### ❌ Erros Comuns

1. **Testar só em 1 período**
   → Pode ter dado sorte!

2. **Ignorar o viés**
   → Modelo pode só funcionar em queda

3. **Acreditar em resultados irreais**
   → Sempre valide em produção

---

## 🚀 Próximos Passos

Depois de validar o modelo:

1. **Se WR >56% e ROI >50% ao ano**: ✅ Modelo bom!
   ```bash
   # Adicione no .env
   MIN_ML_CONFIDENCE=0.10  # Valor recomendado pelo script
   ```

2. **Se WR <54% ou ROI <20% ao ano**: ⚠️ Retreinar
   ```bash
   # Treine com mais dados
   python train_master_scalper_v2.py --days 730
   ```

3. **Se modelo enviesado**: 🔧 Ajustar
   - Reduza consensus no target (70% → 65%)
   - Aumente stopping_rounds (50 → 100)
   - Treine com mais dados (365 → 730 dias)

---

## 📚 Arquivos Relacionados

- `validate_strategy.py` - Script principal (universal loader)
- `train_master_scalper.py` - Treina modelo V1
- `train_master_scalper_v2.py` - Treina modelo V2 (avançado)
- `MODEL_V2_IMPROVEMENTS.md` - Documenta melhorias do V2

---

## 🎯 Resumo

**Antes**:
- ❌ Só funcionava com modelos específicos
- ❌ Erro ao carregar ModelWrapper
- ❌ Precisava ajustar código para cada modelo

**Agora**:
- ✅ Funciona com QUALQUER modelo .pkl
- ✅ Auto-detecta formato e versão
- ✅ Extrai feature_names automaticamente
- ✅ Aplica features corretas (V1 ou V2)
- ✅ Usa threshold otimizado se disponível

**Use com qualquer modelo! 🚀**
