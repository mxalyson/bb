#!/usr/bin/env python3
"""
Verifica a versão do arquivo 1.py e se tem as features necessárias
"""

import os

def check_file():
    filepath = '1.py'

    if not os.path.exists(filepath):
        print(f"❌ Arquivo {filepath} não encontrado")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')

    print(f"📊 Total de linhas: {len(lines)}")
    print()

    # Check for key features
    checks = {
        '_predict_from_wrapper': 'Método _predict_from_wrapper (ensemble support)',
        'models_list': 'Verificação de models_list',
        'create_ultra_scalper_features': 'Função create_ultra_scalper_features',
        'self.trading_fee': 'Taxa da Bybit',
        'Total Fees Paid': 'Display de taxas no summary'
    }

    print("🔍 Verificando features:")
    for key, desc in checks.items():
        if key in content:
            # Find line number
            for i, line in enumerate(lines, 1):
                if key in line:
                    print(f"  ✅ {desc} - linha {i}")
                    break
        else:
            print(f"  ❌ {desc} - NÃO ENCONTRADO")

    print()

    # Check specific line that's failing
    print("🔍 Verificando linha do erro (776-782):")
    if len(lines) > 782:
        for i in range(775, 783):
            if i < len(lines):
                print(f"  {i}: {lines[i][:80]}")
    else:
        print(f"  ⚠️  Arquivo tem apenas {len(lines)} linhas (deveria ter ~1408)")

    print()

    # Check expected line (843)
    print("🔍 Verificando linha esperada (843):")
    if len(lines) > 843:
        for i in range(842, 849):
            if i < len(lines):
                print(f"  {i}: {lines[i][:80]}")
    else:
        print(f"  ⚠️  Arquivo muito curto, não tem linha 843")

if __name__ == '__main__':
    check_file()
