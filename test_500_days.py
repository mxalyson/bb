"""
Teste rápido: Melhor config (25% conf) com 500 dias
"""
import sys
sys.path.append('.')

# Apenas importar se estiver no ambiente com pandas
try:
    import pandas as pd
    import numpy as np
    from core.data import DataManager
    from core.features import FeatureStore
    from core.utils import load_config, setup_logging
    import pickle
    import warnings
    warnings.filterwarnings('ignore')

    logger = setup_logging('INFO', log_to_file=False)
    
    print("🚀 Testando MELHOR CONFIG com 500 dias...")
    print(f"Confiança: 25%")
    print(f"SL: 1.5x ATR | TP: 1.2x ATR")
    print(f"Cooldown: 0 (sem espera)")
    print("="*80)
    
    # Carregar modelo
    with open('trained_model.pkl', 'rb') as f:
        model_data = pickle.load(f)
    
    model = model_data['model']
    feature_names = model_data['feature_names']
    optimal_threshold = model_data.get('optimal_threshold', 0.5)
    
    # Download 500 dias
    config = load_config('standard')
    dm = DataManager(config)
    
    print("\n📥 Baixando 500 dias de dados...")
    df = dm.get_data('BTCUSDT', '15m', 500, use_cache=False)
    print(f"✅ {len(df)} candles baixados ({len(df)/96:.1f} dias)")
    
    # Features
    print("\n🔧 Calculando features...")
    fs = FeatureStore(config)
    df = fs.build_features(df, normalize=False)
    
    # Predição
    print("\n🔮 Fazendo predições...")
    X = df[feature_names].fillna(0).replace([np.inf, -np.inf], 0)
    
    if hasattr(model, 'predict'):
        preds = model.predict(X)
    else:
        preds = model.models_list[0].predict(X)
    
    df['ml_prob_up'] = preds
    df['ml_confidence'] = np.abs(preds - optimal_threshold) * 2
    
    # Sinais com 25% confiança
    df['signal'] = 0
    mask_long = (df['ml_prob_up'] > optimal_threshold) & (df['ml_confidence'] >= 0.25)
    mask_short = (df['ml_prob_up'] < optimal_threshold) & (df['ml_confidence'] >= 0.25)
    df.loc[mask_long, 'signal'] = 1
    df.loc[mask_short, 'signal'] = -1
    
    # Backtest simplificado
    print("\n📊 Simulando trades...")
    
    capital = 100
    trades = []
    position = None
    
    for i, row in df.iterrows():
        # Check exit
        if position:
            entry = position['entry']
            sl = position['sl']
            tp = position['tp']
            direction = position['direction']
            
            hit_sl = False
            hit_tp = False
            
            if direction == 'long':
                if row['low'] <= sl:
                    hit_sl = True
                    exit_price = sl
                elif row['high'] >= tp:
                    hit_tp = True
                    exit_price = tp
            else:
                if row['high'] >= sl:
                    hit_sl = True
                    exit_price = sl
                elif row['low'] <= tp:
                    hit_tp = True
                    exit_price = tp
            
            if hit_sl or hit_tp:
                # Close trade
                if direction == 'long':
                    pnl_pct = ((exit_price - entry) / entry) * 100
                else:
                    pnl_pct = ((entry - exit_price) / entry) * 100
                
                pnl_amt = position['size'] * (pnl_pct / 100)
                fee = position['size'] * 0.00055 * 2
                pnl_net = pnl_amt - fee
                
                capital += pnl_net
                
                trades.append({
                    'win': pnl_net > 0,
                    'pnl': pnl_net,
                    'reason': 'tp' if hit_tp else 'sl'
                })
                
                position = None
        
        # Check entry (cooldown = 0)
        if not position and row['signal'] != 0:
            direction = 'long' if row['signal'] == 1 else 'short'
            price = row['close']
            atr = row.get('atr', price * 0.01)
            
            if direction == 'long':
                sl = price - (atr * 1.5)
                tp = price + (atr * 1.2)
            else:
                sl = price + (atr * 1.5)
                tp = price - (atr * 1.2)
            
            sl_dist = abs((sl - price) / price)
            risk_amt = capital * 0.0075
            size = risk_amt / sl_dist if sl_dist > 0 else capital * 0.1
            size = min(size, capital * 0.95)
            
            position = {
                'entry': price,
                'sl': sl,
                'tp': tp,
                'direction': direction,
                'size': size
            }
    
    # Estatísticas
    if trades:
        wins = [t for t in trades if t['win']]
        losses = [t for t in trades if not t['win']]
        
        wr = len(wins) / len(trades) * 100
        roi = ((capital - 100) / 100) * 100
        
        print("\n" + "="*80)
        print("🏆 RESULTADOS - 500 DIAS")
        print("="*80)
        print(f"📊 Total Trades: {len(trades)}")
        print(f"✅ Wins: {len(wins)}")
        print(f"❌ Losses: {len(losses)}")
        print(f"📈 Win Rate: {wr:.1f}%")
        print(f"💰 ROI: {roi:+,.2f}%")
        print(f"💵 Capital Final: ${capital:,.2f}")
        print(f"📉 Drawdown: Não calculado (simplificado)")
        print("="*80)
        
        # Comparar com 30 dias
        print("\n📊 COMPARAÇÃO:")
        print(f"30 dias (original):  ROI +147,306% | WR 82.2% | 5,992 trades")
        print(f"500 dias (novo):     ROI {roi:+,.0f}% | WR {wr:.1f}% | {len(trades)} trades")
        
        if roi > 50000:
            print("\n✅ VALIDADO! Config funciona bem em longo prazo!")
        elif roi > 10000:
            print("\n⚠️ ROI menor em 500 dias - possível overfitting nos 30 dias")
        else:
            print("\n❌ Config NÃO se sustenta em longo prazo - muito overfitting")

except ImportError as e:
    print(f"❌ Execute este script no seu notebook com pandas instalado")
    print(f"Erro: {e}")

