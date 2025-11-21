"""
SCRIPT DE DIAGNÓSTICO DO BACKTEST
Verifica se o backtest está funcionando corretamente
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

print("=" * 80)
print("🔬 DIAGNÓSTICO DO BACKTEST")
print("=" * 80)
print()

# 1. Verificar estrutura de diretórios
print("1️⃣ Verificando estrutura de diretórios...")
model_in_root = Path("ml_model_master_scalper_365d.pkl").exists()
storage_exists = Path("storage").exists()
models_dir = Path("storage/models").exists()

print(f"   ✅ Modelo na raiz: {model_in_root}")
print(f"   {'✅' if storage_exists else '❌'} storage/: {storage_exists}")
print(f"   {'✅' if models_dir else '❌'} storage/models/: {models_dir}")
print()

# 2. Verificar modelo
print("2️⃣ Verificando modelo...")
if model_in_root:
    import pickle

    class ModelWrapper:
        def __init__(self, model=None, feature_names=None, **kwargs):
            self.model = model
            self.feature_names = feature_names
            self.__dict__.update(kwargs)

    class UniversalUnpickler(pickle.Unpickler):
        def find_class(self, module, name):
            if name == 'ModelWrapper':
                return ModelWrapper
            try:
                return super().find_class(module, name)
            except Exception as e:
                print(f"   ⚠️  Missing class {module}.{name}, using ModelWrapper")
                return ModelWrapper

    try:
        with open("ml_model_master_scalper_365d.pkl", 'rb') as f:
            model_data = UniversalUnpickler(f).load()

        if isinstance(model_data, dict):
            print(f"   ✅ Modelo carregado (dict)")
            print(f"   ✅ Features: {len(model_data.get('feature_names', []))}")
            print(f"   ✅ Threshold: {model_data.get('optimal_threshold', 0.5):.3f}")

            # Mostrar algumas features
            features = model_data.get('feature_names', [])
            if features:
                print(f"   📋 Primeiras features: {features[:5]}")
        else:
            print(f"   ⚠️  Modelo carregado mas formato inesperado: {type(model_data)}")
            if hasattr(model_data, 'feature_names'):
                print(f"   ✅ Features: {len(model_data.feature_names)}")

        print()

    except Exception as e:
        print(f"   ❌ Erro ao carregar modelo: {e}")
        print()
else:
    print(f"   ❌ Modelo não encontrado na raiz")
    print()

# 3. Verificar dependências
print("3️⃣ Verificando dependências...")
dependencies = {
    'pandas': None,
    'numpy': None,
    'sklearn': 'scikit-learn',
    'scipy': None,
    'pybit': None
}

for module, package in dependencies.items():
    try:
        __import__(module)
        print(f"   ✅ {package or module}")
    except ImportError:
        print(f"   ❌ {package or module} (pip install {package or module})")

print()

# 4. Verificar config
print("4️⃣ Verificando configuração...")
env_example = Path(".env.example").exists()
env_file = Path(".env").exists()

print(f"   {'✅' if env_example else '❌'} .env.example: {env_example}")
print(f"   {'✅' if env_file else '❌'} .env: {env_file}")

if not env_file:
    print(f"   ⚠️  .env não existe - crie a partir do .env.example")

print()

# 5. Testar conexão API (se .env existir)
print("5️⃣ Testando conexão Bybit API...")
if env_file:
    try:
        from core.utils import load_config
        config = load_config('standard')

        # Verificar se tem API keys
        has_key = config.get('bybit_api_key') and len(config.get('bybit_api_key', '')) > 10
        has_secret = config.get('bybit_api_secret') and len(config.get('bybit_api_secret', '')) > 10
        is_testnet = config.get('bybit_testnet', True)

        print(f"   {'✅' if has_key else '❌'} API Key configurada: {has_key}")
        print(f"   {'✅' if has_secret else '❌'} API Secret configurada: {has_secret}")
        print(f"   🌐 Testnet: {is_testnet}")

        if has_key and has_secret:
            try:
                from core.bybit_rest import BybitRESTClient
                client = BybitRESTClient(
                    api_key=config['bybit_api_key'],
                    api_secret=config['bybit_api_secret'],
                    testnet=is_testnet
                )

                # Tentar pegar server time
                info = client.rest_client.get_server_time()
                if info and info.get('retCode') == 0:
                    print(f"   ✅ Conexão OK - Server time: {info.get('result', {}).get('timeSecond')}")
                else:
                    print(f"   ⚠️  Resposta inesperada da API: {info}")
            except Exception as e:
                print(f"   ❌ Erro na conexão: {e}")

    except Exception as e:
        print(f"   ❌ Erro ao carregar config: {e}")
else:
    print(f"   ⏭️  Pulando (sem .env)")

print()

# 6. Verificar estrutura de arquivos necessários
print("6️⃣ Verificando arquivos necessários...")
required_files = {
    '1.py': 'Script de backtest',
    'live_bot.py': 'Bot de trading ao vivo',
    'core/utils.py': 'Utilities',
    'core/bybit_rest.py': 'Cliente Bybit REST',
    'core/data.py': 'Data Manager',
    'core/features.py': 'Feature Store'
}

for file, desc in required_files.items():
    exists = Path(file).exists()
    print(f"   {'✅' if exists else '❌'} {file} ({desc})")

print()

# 7. Resumo e recomendações
print("=" * 80)
print("📊 RESUMO DO DIAGNÓSTICO")
print("=" * 80)
print()

# Verificar o que está faltando
issues = []
fixes = []

if not storage_exists or not models_dir:
    issues.append("❌ Estrutura de diretórios incompleta")
    fixes.append("   mkdir -p storage/models")

if model_in_root and not Path("storage/models/ml_model_master_scalper_365d.pkl").exists():
    issues.append("❌ Modelo está na raiz mas backtest espera em storage/models/")
    fixes.append("   mv ml_model_master_scalper_365d.pkl storage/models/")

if not env_file:
    issues.append("❌ Arquivo .env não existe")
    fixes.append("   cp .env.example .env")
    fixes.append("   # Edite .env e adicione suas API keys da Bybit")

try:
    import pandas
    import numpy
    import sklearn
    deps_ok = True
except ImportError:
    deps_ok = False
    issues.append("❌ Dependências Python faltando")
    fixes.append("   pip install pandas numpy scikit-learn scipy pybit python-dotenv")

if not issues:
    print("✅ TUDO OK! O backtest está pronto para rodar!")
    print()
    print("🚀 Para rodar o backtest:")
    print("   python 1.py --symbol BTCUSDT --days 180 --fee-type taker")
    print()
    print("📊 Opções:")
    print("   --verbose-trades    Mostrar cada trade individual")
    print("   --days 90           Testar com 90 dias")
    print("   --fee-type maker    Usar maker fees (0.02%)")
else:
    print("⚠️  PROBLEMAS ENCONTRADOS:")
    print()
    for issue in issues:
        print(issue)
    print()
    print("🔧 COMO CORRIGIR:")
    print()
    for fix in fixes:
        print(fix)

print()
print("=" * 80)
