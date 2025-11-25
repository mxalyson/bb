#!/usr/bin/env python3
"""
Simple feature extraction without loading the full model.
"""

import pickle
import sys

print("\n" + "=" * 80)
print("🔍 EXTRAINDO FEATURES DO MODELO")
print("=" * 80)
print()

# Try to load just the metadata
try:
    # First, try to peek at the pickle without full deserialization
    with open('ml_model_master_scalper_365d.pkl', 'rb') as f:
        # Try to load with restricted unpickler
        import pickletools
        pickletools.dis(f, annotate=1)

except Exception as e:
    print(f"❌ Erro: {e}")
    print()
    print("💡 Não é possível extrair features sem o LightGBM instalado.")
    print()
    print("ALTERNATIVA: Vou buscar as features nos logs do treinamento...")

    # Try to find training logs
    import os
    import re

    # Check if there are any training logs
    log_files = [f for f in os.listdir('.') if 'train' in f.lower() and f.endswith('.log')]

    if log_files:
        print(f"\n📝 Encontrados {len(log_files)} arquivos de log:")
        for log_file in log_files:
            print(f"   - {log_file}")
    else:
        print("\n❌ Nenhum log de treinamento encontrado")
        print()
        print("SOLUÇÃO: Execute o train_master_scalper.py para ver as features:")
        print("   python3 train_master_scalper.py --symbol BTCUSDT --days 365")
