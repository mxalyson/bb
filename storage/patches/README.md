# 🔒 CRITICAL FIX: Live Bot Capital Limit

## ⚠️ PROBLEMA ENCONTRADO

O bot live (`live_bot.py`) **NÃO tinha limite máximo** de capital por trade, enquanto o backtest (`1.py`) tinha proteção de 95%.

Isso significa que o bot poderia usar **100%+ do capital** em uma única operação, o que é **EXTREMAMENTE PERIGOSO** para trading ao vivo!

## ✅ SOLUÇÃO APLICADA

Adicionado limite de **95% do capital** em `live_bot.py` para igualar ao backtest.

### Comparação:

| Aspecto | Backtest (1.py) | Live Bot (ANTES) | Live Bot (DEPOIS) |
|---------|-----------------|------------------|-------------------|
| **Limite mínimo** | ✅ 0.001 BTC | ✅ 0.001 BTC | ✅ 0.001 BTC |
| **Arredondamento** | ✅ 0.001 steps | ✅ 0.001 steps | ✅ 0.001 steps |
| **Limite máximo** | ✅ 95% capital | ❌ **SEM LIMITE** | ✅ **95% capital** |

## 📝 COMO APLICAR O PATCH

Se você está em outra máquina e precisa aplicar essa correção:

```bash
# Opção 1: Aplicar o patch
cd /caminho/para/bb
git apply storage/patches/0001-CRITICAL-Add-95-capital-limit-to-live_bot.py.patch

# Opção 2: Cherry-pick do commit
git cherry-pick 9a7ddbc
```

## 🔍 CÓDIGO ALTERADO

**Arquivo:** `live_bot.py`
**Função:** `calculate_position_size()`
**Linhas:** 705-710

```python
# CRITICAL: Limit to 95% of capital (same as 1.py line 1082)
size_usd = qty_btc * price
max_size_usd = self.capital * 0.95
if size_usd > max_size_usd:
    qty_btc = max_size_usd / price
    qty_btc = max(self.min_qty, qty_btc)  # Ensure still above minimum
```

## 📊 COMMITS

```
9a7ddbc - 🔒 CRITICAL: Add 95% capital limit to live_bot.py
cd86c9f - Add .gitignore for Python project
```

## ⚠️ NOTA SOBRE PUSH

Estes commits **não puderam ser enviados** para a branch `claude/debug-bot-model-size-017dwMhKdJYZv1jDjVCQ4Ujs` devido a erro 403 (permissões).

**As mudanças estão salvas localmente e nos patches acima.**

## 🛡️ IMPORTÂNCIA

Esta correção é **CRÍTICA** para segurança do capital. Sem ela, o bot pode:
- Usar 100% do capital em 1 trade
- Não ter margem para fees
- Ficar vulnerável a liquidação
- Resultados de backtest não refletirem realidade

**SEMPRE use o limite de 95% em produção!**
