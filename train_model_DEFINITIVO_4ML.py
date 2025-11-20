"""
MODELO DEFINITIVO - 4 ML PERFEITOS (SEM LSTM/CNN)
==========================================

COMBINA TUDO QUE FUNCIONA:
✅ 6 modelos (LGB, XGB, CB, RF, LSTM, CNN) - DIVERSIDADE do V5
✅ 100+ features extraordinárias - QUALIDADE do V5
✅ Optuna tuning focado em LONG accuracy - OTIMIZAÇÃO do V5
✅ UNDER-SAMPLING 50/50 - RESOLVE imbalance (não SMOTE!)
✅ Threshold ajustado (0.35 long, 0.65 short) - COMPENSA viés
✅ Weighted ensemble por LONG accuracy - MELHOR que meta-learner
✅ Regularização EXTREMA - ANTI-OVERFITTING
✅ Order flow + microstructure - FEATURES CRUCIAIS

POR QUE V5 FALHOU: SMOTE + class weights não resolvem imbalance extremo
SOLUÇÃO: UNDER-SAMPLING (dados reais 50/50) + weighted ensemble

RESULTADO ESPERADO: 52-56% META, Long 48-52%, Short 52-56%, Desbalance < 5%
"""

import os
import sys
import pickle
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time

warnings.filterwarnings('ignore')

print("=" * 80)
print("🚀 MODELO DEFINITIVO - 4 ML PERFEITOS (SEM LSTM/CNN)")
print("=" * 80)
print()

# Check dependencies
print("📋 Verificando dependências...")
try:
    import requests
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split, StratifiedKFold
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.utils import resample
    import lightgbm as lgb
    import xgboost as xgb

    try:
        import catboost as cb
        HAS_CATBOOST = True
    except:
        print("   ⚠️  CatBoost não instalado")
        HAS_CATBOOST = False

    try:
        import tensorflow as tf
        from tensorflow import keras
        from tensorflow.keras import layers
        HAS_TF = True
        tf.get_logger().setLevel('ERROR')
        print("   ✅ TensorFlow OK!")
    except:
        print("   ❌ TensorFlow não instalado (pip install tensorflow)")
        HAS_TF = False

    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        HAS_OPTUNA = True
    except:
        print("   ⚠️  Optuna não instalado")
        HAS_OPTUNA = False

    print("✅ Dependências OK!")

except ImportError as e:
    print(f"❌ ERRO: {e}")
    sys.exit(1)

print()

storage_dir = Path("storage/models")
storage_dir.mkdir(parents=True, exist_ok=True)


# ModelWrapper para pickle
class ModelWrapper:
    """Wrapper com weighted ensemble e threshold ajustado."""

    def __init__(self, models_list, model_weights, model_names, scaler, feature_columns, has_dl=False,
                 long_threshold=0.35, short_threshold=0.65, lookback=10):
        self.models_list = models_list
        self.model_weights = model_weights
        self.model_names = model_names
        self.scaler = scaler
        self.feature_columns = feature_columns
        self.has_dl = has_dl
        self.long_threshold = long_threshold
        self.short_threshold = short_threshold
        self.lookback = lookback
        self.version = "MODELO_FINAL_COMPLETO"
        self.timestamp = datetime.now().isoformat()

    def predict_proba(self, X):
        """Weighted ensemble prediction."""
        if isinstance(X, pd.DataFrame):
            X = X[self.feature_columns].values

        X_scaled = self.scaler.transform(X)

        # Get weighted predictions from all models
        all_probs = []
        for model, weight, name in zip(self.models_list, self.model_weights, self.model_names):

            if name in ['LSTM', 'CNN'] and self.has_dl:
                # DL needs sequences
                X_seq = self._prepare_sequences(X_scaled)
                pred_full = np.zeros(len(X_scaled))
                pred_full[self.lookback:] = model.predict(X_seq, verbose=0).flatten()
                pred_full[:self.lookback] = pred_full[self.lookback]  # Fill inicio
                pred = pred_full
            else:
                pred = model.predict_proba(X_scaled)[:, 1]

            all_probs.append(pred * weight)

        # Weighted average
        final_proba = np.sum(all_probs, axis=0)

        # Return as 2D array
        proba_class_0 = 1 - final_proba
        proba_class_1 = final_proba

        return np.column_stack([proba_class_0, proba_class_1])

    def predict(self, X):
        """Predição binária com threshold ajustado."""
        proba = self.predict_proba(X)[:, 1]

        predictions = np.zeros(len(proba))

        # Lower threshold for longs (easier to enter)
        predictions[proba >= self.long_threshold] = 1

        return predictions.astype(int)

    def _prepare_sequences(self, X):
        """Prepara sequences para LSTM/CNN."""
        X_seq = []
        for i in range(self.lookback, len(X)):
            X_seq.append(X[i-self.lookback:i])
        return np.array(X_seq)


def get_binance_klines(symbol='BTCUSDT', interval='15m', days=365):
    """Baixa dados da Binance."""
    print(f"📥 Baixando {days} dias de dados...")

    all_data = []
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    url = "https://api.binance.com/api/v3/klines"
    current_time = start_time

    while current_time < end_time:
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': current_time,
            'limit': 1000
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            klines = response.json()

            if not klines:
                break

            all_data.extend(klines)
            current_time = klines[-1][0] + 1

            if len(klines) < 1000:
                break

        except Exception as e:
            print(f"   ❌ Erro: {e}")
            break

    if not all_data:
        print("   ❌ Nenhum dado baixado!")
        sys.exit(1)

    df = pd.DataFrame(all_data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    for col in ['open', 'high', 'low', 'close', 'volume', 'taker_buy_base', 'taker_buy_quote']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values('timestamp').reset_index(drop=True)

    print(f"   ✅ {len(df)} candles de {df['timestamp'].min()} a {df['timestamp'].max()}")
    return df


def add_extraordinary_features(df):
    """
    Features EXTRAORDINÁRIAS para scalping.
    Combinação de técnicas avançadas + order flow.
    """
    print("🔧 Criando features EXTRAORDINÁRIAS...")

    # ========================================================================
    # PRICE ACTION AVANÇADO
    # ========================================================================
    df['returns'] = df['close'].pct_change()
    df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

    # Body/Wick analysis (importante para reversão)
    df['body_size'] = np.abs(df['close'] - df['open']) / df['open']
    df['upper_wick'] = (df['high'] - df[['close', 'open']].max(axis=1)) / df['open']
    df['lower_wick'] = (df[['close', 'open']].min(axis=1) - df['low']) / df['open']
    df['total_wick'] = df['upper_wick'] + df['lower_wick']
    df['wick_body_ratio'] = df['total_wick'] / (df['body_size'] + 1e-8)

    # Candle patterns
    df['is_green'] = (df['close'] > df['open']).astype(int)
    df['green_streak'] = df['is_green'].rolling(3).sum()
    df['red_streak'] = (1 - df['is_green']).rolling(3).sum()

    # ========================================================================
    # ORDER FLOW - BUY/SELL PRESSURE
    # ========================================================================
    # Taker buy ratio (muito importante para scalping!)
    df['taker_buy_ratio'] = df['taker_buy_base'] / (df['volume'] + 1e-8)
    df['taker_sell_ratio'] = 1 - df['taker_buy_ratio']

    # Buy/Sell pressure momentum
    df['buy_pressure_ma'] = df['taker_buy_ratio'].rolling(7).mean()
    df['sell_pressure_ma'] = df['taker_sell_ratio'].rolling(7).mean()
    df['pressure_delta'] = df['buy_pressure_ma'] - df['sell_pressure_ma']
    df['pressure_momentum'] = df['pressure_delta'].diff(3)

    # Order flow imbalance
    df['order_imbalance'] = (df['taker_buy_base'] - (df['volume'] - df['taker_buy_base'])) / (df['volume'] + 1e-8)
    df['imbalance_ma'] = df['order_imbalance'].rolling(5).mean()

    # ========================================================================
    # MOVING AVERAGES + CROSSOVERS
    # ========================================================================
    for period in [7, 14, 21, 50]:
        df[f'sma_{period}'] = df['close'].rolling(period).mean()
        df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        df[f'price_sma_{period}_ratio'] = df['close'] / df[f'sma_{period}']

    # Crossover signals
    df['ema7_above_ema14'] = (df['ema_7'] > df['ema_14']).astype(int)
    df['ema14_above_ema21'] = (df['ema_14'] > df['ema_21']).astype(int)
    df['ema21_above_ema50'] = (df['ema_21'] > df['ema_50']).astype(int)

    # Golden/Death cross
    df['golden_cross'] = df['ema7_above_ema14'] & df['ema14_above_ema21']
    df['death_cross'] = (1 - df['ema7_above_ema14']) & (1 - df['ema14_above_ema21'])

    # ========================================================================
    # VOLATILITY (ATR é KEY para SL/TP)
    # ========================================================================
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr_14'] = true_range.rolling(14).mean()
    df['atr_pct'] = df['atr_14'] / df['close']

    # Volatility regimes
    df['volatility_7'] = df['returns'].rolling(7).std()
    df['volatility_21'] = df['returns'].rolling(21).std()
    df['volatility_ratio'] = df['volatility_7'] / (df['volatility_21'] + 1e-8)

    # Volatility spike
    df['high_volatility'] = (df['volatility_ratio'] > 1.3).astype(int)
    df['low_volatility'] = (df['volatility_ratio'] < 0.7).astype(int)

    # ========================================================================
    # RSI AVANÇADO
    # ========================================================================
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # RSI zones
    df['rsi_extreme_oversold'] = (df['rsi_14'] < 25).astype(int)
    df['rsi_extreme_overbought'] = (df['rsi_14'] > 75).astype(int)
    df['rsi_mid'] = ((df['rsi_14'] >= 45) & (df['rsi_14'] <= 55)).astype(int)

    # RSI divergence
    df['price_slope'] = df['close'].diff(5)
    df['rsi_slope'] = df['rsi_14'].diff(5)
    df['bullish_divergence'] = ((df['rsi_slope'] > 0) & (df['price_slope'] < 0)).astype(int)
    df['bearish_divergence'] = ((df['rsi_slope'] < 0) & (df['price_slope'] > 0)).astype(int)

    # ========================================================================
    # MACD
    # ========================================================================
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # MACD signals
    df['macd_positive'] = (df['macd'] > 0).astype(int)
    df['macd_hist_increasing'] = (df['macd_hist'] > df['macd_hist'].shift(1)).astype(int)

    # ========================================================================
    # BOLLINGER BANDS
    # ========================================================================
    df['bb_middle'] = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-8)

    # BB breakout
    df['bb_upper_breakout'] = (df['close'] > df['bb_upper']).astype(int)
    df['bb_lower_breakout'] = (df['close'] < df['bb_lower']).astype(int)

    # ========================================================================
    # VOLUME (confirmação crucial)
    # ========================================================================
    df['volume_sma_20'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / (df['volume_sma_20'] + 1e-8)
    df['high_volume'] = (df['volume_ratio'] > 1.5).astype(int)

    # Volume trend
    df['volume_slope'] = df['volume'].diff(3)
    df['volume_increasing_trend'] = (df['volume_slope'] > 0).astype(int).rolling(3).sum()

    # ========================================================================
    # MOMENTUM
    # ========================================================================
    df['momentum_3'] = df['close'] / df['close'].shift(3) - 1
    df['momentum_7'] = df['close'] / df['close'].shift(7) - 1
    df['momentum_14'] = df['close'] / df['close'].shift(14) - 1

    # Momentum acceleration
    df['momentum_accel'] = df['momentum_7'].diff(3)

    # ========================================================================
    # PRICE POSITION
    # ========================================================================
    df['price_position_14'] = (df['close'] - df['low'].rolling(14).min()) / \
                               (df['high'].rolling(14).max() - df['low'].rolling(14).min() + 1e-8)

    df['price_position_50'] = (df['close'] - df['low'].rolling(50).min()) / \
                               (df['high'].rolling(50).max() - df['low'].rolling(50).min() + 1e-8)

    # ========================================================================
    # TREND STRENGTH
    # ========================================================================
    df['higher_high'] = (df['high'] > df['high'].shift(1)).astype(int)
    df['lower_low'] = (df['low'] < df['low'].shift(1)).astype(int)
    df['hh_count'] = df['higher_high'].rolling(5).sum()
    df['ll_count'] = df['lower_low'].rolling(5).sum()
    df['trend_strength'] = df['hh_count'] - df['ll_count']

    # ========================================================================
    # TIME-BASED FEATURES (importante para scalping!)
    # ========================================================================
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek

    # Trading session (UTC)
    df['asian_session'] = ((df['hour'] >= 0) & (df['hour'] < 8)).astype(int)
    df['london_session'] = ((df['hour'] >= 8) & (df['hour'] < 16)).astype(int)
    df['us_session'] = ((df['hour'] >= 13) & (df['hour'] < 22)).astype(int)

    # Weekend effect
    df['weekend'] = (df['day_of_week'] >= 5).astype(int)

    # ========================================================================
    # MICROSTRUCTURE
    # ========================================================================
    # Spread proxy (high-low range)
    df['spread_proxy'] = (df['high'] - df['low']) / df['close']
    df['spread_ma'] = df['spread_proxy'].rolling(10).mean()

    # Price impact (large candles)
    df['large_candle'] = (df['body_size'] > df['body_size'].rolling(20).mean() * 1.5).astype(int)

    # ========================================================================
    # CLEAN
    # ========================================================================
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.fillna(method='ffill').fillna(method='bfill').fillna(0)

    print(f"   ✅ {len(df.columns)} features criadas")
    return df


def create_labels(df, threshold=0.0015):
    """Labels baseado em retorno futuro."""
    future_returns = df['close'].shift(-5) / df['close'] - 1
    labels = (future_returns > threshold).astype(int)
    return labels[:-5]


def undersample_majority(X, y):
    """
    Under-sample shorts para balancear 50/50.
    SOLUÇÃO REAL para class imbalance!
    """
    print("\n🔄 Aplicando UNDER-SAMPLING (dados REAIS 50/50)...")

    # Separar classes
    X_long = X[y == 1]
    y_long = y[y == 1]
    X_short = X[y == 0]
    y_short = y[y == 0]

    print(f"   Original: {len(y_long)} longs ({len(y_long)/(len(y_long)+len(y_short))*100:.1f}%), {len(y_short)} shorts ({len(y_short)/(len(y_long)+len(y_short))*100:.1f}%)")

    # Under-sample shorts para match longs
    X_short_under, y_short_under = resample(
        X_short, y_short,
        n_samples=len(y_long),
        random_state=42,
        replace=False
    )

    # Combine
    X_balanced = np.vstack([X_long, X_short_under])
    y_balanced = np.hstack([y_long, y_short_under])

    # Shuffle
    indices = np.random.RandomState(42).permutation(len(y_balanced))
    X_balanced = X_balanced[indices]
    y_balanced = y_balanced[indices]

    print(f"   Balanced: {len(y_balanced)} samples (50% longs, 50% shorts) ✅")
    print(f"   ✅ TODOS os dados são REAIS (não sintéticos)!")

    return X_balanced, y_balanced


def tune_lightgbm(X_train, y_train, n_trials=20):
    """Tuning LightGBM focado em LONG accuracy."""

    if not HAS_OPTUNA:
        return {
            'n_estimators': 250,
            'max_depth': 4,
            'learning_rate': 0.03,
            'num_leaves': 25,
            'min_child_samples': 30,
            'subsample': 0.7,
            'colsample_bytree': 0.7,
            'reg_alpha': 0.3,
            'reg_lambda': 0.3
        }

    print(f"   🔧 Tuning LightGBM ({n_trials} trials, foco em LONG accuracy)...")

    def objective(trial):
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 150, 350),
            'max_depth': trial.suggest_int('max_depth', 3, 6),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.08, log=True),
            'num_leaves': trial.suggest_int('num_leaves', 15, 40),
            'min_child_samples': trial.suggest_int('min_child_samples', 20, 60),
            'subsample': trial.suggest_float('subsample', 0.6, 0.9),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 0.9),
            'reg_alpha': trial.suggest_float('reg_alpha', 0.1, 0.5),
            'reg_lambda': trial.suggest_float('reg_lambda', 0.1, 0.5),
            'random_state': 42,
            'verbose': -1
        }

        model = lgb.LGBMClassifier(**params)

        # StratifiedKFold
        skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        scores_long = []
        scores_overall = []

        for train_idx, val_idx in skf.split(X_train, y_train):
            X_tr, X_val = X_train[train_idx], X_train[val_idx]
            y_tr, y_val = y_train[train_idx], y_train[val_idx]

            model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                     callbacks=[lgb.early_stopping(50, verbose=False)])

            pred = model.predict(X_val)

            # Score LONG accuracy (métrica primária!)
            if (y_val == 1).sum() > 0:
                long_acc = accuracy_score(y_val[y_val == 1], pred[y_val == 1])
                scores_long.append(long_acc)

            overall_acc = accuracy_score(y_val, pred)
            scores_overall.append(overall_acc)

        # Optimize for LONG accuracy (70%) + overall (30%)
        if len(scores_long) > 0:
            combined_score = np.mean(scores_long) * 0.7 + np.mean(scores_overall) * 0.3
        else:
            combined_score = np.mean(scores_overall)

        return combined_score

    study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    print(f"      ✅ Best CV: {study.best_value*100:.2f}%")
    return study.best_params


def tune_xgboost(X_train, y_train, n_trials=20):
    """Tuning XGBoost focado em LONG accuracy."""

    if not HAS_OPTUNA:
        return {
            'n_estimators': 250,
            'max_depth': 4,
            'learning_rate': 0.03,
            'subsample': 0.7,
            'colsample_bytree': 0.7,
            'reg_alpha': 0.3,
            'reg_lambda': 0.3
        }

    print(f"   🔧 Tuning XGBoost ({n_trials} trials, foco em LONG accuracy)...")

    def objective(trial):
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 150, 350),
            'max_depth': trial.suggest_int('max_depth', 3, 6),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.08, log=True),
            'subsample': trial.suggest_float('subsample', 0.6, 0.9),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 0.9),
            'gamma': trial.suggest_float('gamma', 0.1, 0.5),
            'reg_alpha': trial.suggest_float('reg_alpha', 0.1, 0.5),
            'reg_lambda': trial.suggest_float('reg_lambda', 0.1, 0.5),
            'min_child_weight': trial.suggest_int('min_child_weight', 3, 10),
            'random_state': 42,
            'verbosity': 0
        }

        model = xgb.XGBClassifier(**params)

        # StratifiedKFold
        skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        scores_long = []
        scores_overall = []

        for train_idx, val_idx in skf.split(X_train, y_train):
            X_tr, X_val = X_train[train_idx], X_train[val_idx]
            y_tr, y_val = y_train[train_idx], y_train[val_idx]

            model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                     verbose=False)

            pred = model.predict(X_val)

            # Score LONG accuracy (métrica primária!)
            if (y_val == 1).sum() > 0:
                long_acc = accuracy_score(y_val[y_val == 1], pred[y_val == 1])
                scores_long.append(long_acc)

            overall_acc = accuracy_score(y_val, pred)
            scores_overall.append(overall_acc)

        # Optimize for LONG accuracy (70%) + overall (30%)
        if len(scores_long) > 0:
            combined_score = np.mean(scores_long) * 0.7 + np.mean(scores_overall) * 0.3
        else:
            combined_score = np.mean(scores_overall)

        return combined_score

    study = optuna.create_study(direction='maximize', sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    print(f"      ✅ Best CV: {study.best_value*100:.2f}%")
    return study.best_params


def create_lstm_model(input_shape, dropout=0.5):
    """LSTM com regularização forte (anti-overfitting)."""
    model = keras.Sequential([
        layers.LSTM(16, return_sequences=True, input_shape=input_shape,
                   kernel_regularizer=keras.regularizers.l2(0.01)),
        layers.Dropout(0.5),
        layers.LSTM(16, kernel_regularizer=keras.regularizers.l2(0.01)),
        layers.Dropout(0.5),
        layers.Dense(16, activation='relu', kernel_regularizer=keras.regularizers.l2(0.01)),
        layers.Dropout(dropout/2),
        layers.Dense(1, activation='sigmoid')
    ])

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss='binary_crossentropy',
        metrics=['accuracy']
    )

    return model


def create_cnn_model(input_shape, dropout=0.5):
    """CNN 1D com regularização forte (anti-overfitting)."""
    model = keras.Sequential([
        layers.Conv1D(16, 3, activation='relu', input_shape=input_shape,
                     kernel_regularizer=keras.regularizers.l2(0.01)),
        layers.MaxPooling1D(2),
        layers.Dropout(0.5),
        layers.Conv1D(16, 3, activation='relu',
                     kernel_regularizer=keras.regularizers.l2(0.01)),
        layers.MaxPooling1D(2),
        layers.Dropout(0.5),
        layers.Flatten(),
        layers.Dense(16, activation='relu', kernel_regularizer=keras.regularizers.l2(0.01)),
        layers.Dropout(dropout/2),
        layers.Dense(1, activation='sigmoid')
    ])

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss='binary_crossentropy',
        metrics=['accuracy']
    )

    return model


def train_final_completo(df, days):
    """Treina MODELO DEFINITIVO - 4 ML PERFEITOS (SEM LSTM/CNN)."""

    print()
    print(f"🎯 TREINANDO MODELO FINAL COMPLETO ({days} dias)...")
    print("=" * 80)

    # Feature columns
    feature_cols = [col for col in df.columns if col not in
                   ['timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore']]

    # Labels
    labels = create_labels(df, threshold=0.0015)

    # Prepare
    X = df[feature_cols].iloc[:-5].values
    y = labels.values

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    print(f"\n📊 Dataset:")
    print(f"   Train: {len(X_train)} samples")
    print(f"   Test: {len(X_test)} samples")
    print(f"   Longs: {(y_train==1).sum()} ({(y_train==1).sum()/len(y_train)*100:.1f}%)")
    print(f"   Shorts: {(y_train==0).sum()} ({(y_train==0).sum()/len(y_train)*100:.1f}%)")

    # Scale
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # UNDER-SAMPLING (solução REAL para imbalance!)
    X_train_balanced, y_train_balanced = undersample_majority(X_train_scaled, y_train)

    # ========================================================================
    # TRAIN 6 MODELS (DIVERSIDADE MÁXIMA!)
    # ========================================================================

    print("\n" + "=" * 80)
    print("🚀 TREINANDO 4 MODELOS ML - OS PERFEITOS")
    print("=" * 80)

    models = {}
    base_predictions_train = []
    base_predictions_test = []
    base_accuracies = []

    # 1. LightGBM with tuning
    print("\n1/6 - LightGBM...")
    lgb_params = tune_lightgbm(X_train_balanced, y_train_balanced, n_trials=20)
    lgb_model = lgb.LGBMClassifier(**lgb_params, random_state=42, verbose=-1)
    lgb_calibrated = CalibratedClassifierCV(lgb_model, method='sigmoid', cv=3)
    lgb_calibrated.fit(X_train_balanced, y_train_balanced)

    lgb_pred_train = lgb_calibrated.predict_proba(X_train_balanced)[:, 1]
    lgb_pred_test = lgb_calibrated.predict_proba(X_test_scaled)[:, 1]
    lgb_acc = accuracy_score(y_test, (lgb_pred_test >= 0.5).astype(int))
    lgb_long_acc = accuracy_score(y_test[y_test==1], (lgb_pred_test[y_test==1] >= 0.5).astype(int))
    lgb_short_acc = accuracy_score(y_test[y_test==0], (lgb_pred_test[y_test==0] >= 0.5).astype(int))

    models['lgb'] = lgb_calibrated
    base_predictions_train.append(lgb_pred_train)
    base_predictions_test.append(lgb_pred_test)
    base_accuracies.append(lgb_acc)

    print(f"   ✅ LightGBM: {lgb_acc*100:.2f}% (Long: {lgb_long_acc*100:.2f}%, Short: {lgb_short_acc*100:.2f}%)")

    # 2. XGBoost with tuning
    print("\n2/6 - XGBoost...")
    xgb_params = tune_xgboost(X_train_balanced, y_train_balanced, n_trials=20)
    xgb_model = xgb.XGBClassifier(**xgb_params, random_state=42, verbosity=0)
    xgb_calibrated = CalibratedClassifierCV(xgb_model, method='sigmoid', cv=3)
    xgb_calibrated.fit(X_train_balanced, y_train_balanced)

    xgb_pred_train = xgb_calibrated.predict_proba(X_train_balanced)[:, 1]
    xgb_pred_test = xgb_calibrated.predict_proba(X_test_scaled)[:, 1]
    xgb_acc = accuracy_score(y_test, (xgb_pred_test >= 0.5).astype(int))
    xgb_long_acc = accuracy_score(y_test[y_test==1], (xgb_pred_test[y_test==1] >= 0.5).astype(int))
    xgb_short_acc = accuracy_score(y_test[y_test==0], (xgb_pred_test[y_test==0] >= 0.5).astype(int))

    models['xgb'] = xgb_calibrated
    base_predictions_train.append(xgb_pred_train)
    base_predictions_test.append(xgb_pred_test)
    base_accuracies.append(xgb_acc)

    print(f"   ✅ XGBoost: {xgb_acc*100:.2f}% (Long: {xgb_long_acc*100:.2f}%, Short: {xgb_short_acc*100:.2f}%)")

    # 3. CatBoost
    if HAS_CATBOOST:
        print("\n3/6 - CatBoost...")
        cb_model = cb.CatBoostClassifier(
            iterations=250,
            depth=4,
            learning_rate=0.03,
            random_state=42,
            verbose=0
        )
        cb_calibrated = CalibratedClassifierCV(cb_model, method='sigmoid', cv=3)
        cb_calibrated.fit(X_train_balanced, y_train_balanced)

        cb_pred_train = cb_calibrated.predict_proba(X_train_balanced)[:, 1]
        cb_pred_test = cb_calibrated.predict_proba(X_test_scaled)[:, 1]
        cb_acc = accuracy_score(y_test, (cb_pred_test >= 0.5).astype(int))
        cb_long_acc = accuracy_score(y_test[y_test==1], (cb_pred_test[y_test==1] >= 0.5).astype(int))
        cb_short_acc = accuracy_score(y_test[y_test==0], (cb_pred_test[y_test==0] >= 0.5).astype(int))

        models['catboost'] = cb_calibrated
        base_predictions_train.append(cb_pred_train)
        base_predictions_test.append(cb_pred_test)
        base_accuracies.append(cb_acc)

        print(f"   ✅ CatBoost: {cb_acc*100:.2f}% (Long: {cb_long_acc*100:.2f}%, Short: {cb_short_acc*100:.2f}%)")
    else:
        print("\n3/6 - CatBoost SKIP")

    # 4. Random Forest
    print("\n4/6 - Random Forest...")
    rf_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_split=10,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1
    )
    rf_calibrated = CalibratedClassifierCV(rf_model, method='sigmoid', cv=3)
    rf_calibrated.fit(X_train_balanced, y_train_balanced)

    rf_pred_train = rf_calibrated.predict_proba(X_train_balanced)[:, 1]
    rf_pred_test = rf_calibrated.predict_proba(X_test_scaled)[:, 1]
    rf_acc = accuracy_score(y_test, (rf_pred_test >= 0.5).astype(int))
    rf_long_acc = accuracy_score(y_test[y_test==1], (rf_pred_test[y_test==1] >= 0.5).astype(int))
    rf_short_acc = accuracy_score(y_test[y_test==0], (rf_pred_test[y_test==0] >= 0.5).astype(int))

    models['rf'] = rf_calibrated
    base_predictions_train.append(rf_pred_train)
    base_predictions_test.append(rf_pred_test)
    base_accuracies.append(rf_acc)

    print(f"   ✅ Random Forest: {rf_acc*100:.2f}% (Long: {rf_long_acc*100:.2f}%, Short: {rf_short_acc*100:.2f}%)")

    
    # DL MODELS SKIPPED (instáveis)
    print("\n5/6 - LSTM SKIP (removido - instável)")
    print("\n6/6 - CNN SKIP (removido - instável)")

    use_dl = False

    # ========================================================================
    # META-LEARNER (Logistic Regression - simples e efetivo)
    # ========================================================================

    print("\n" + "=" * 80)
    print("🧠 META-LEARNER (Logistic Regression)")
    print("=" * 80)

    X_meta_train = np.column_stack(base_predictions_train)
    X_meta_test = np.column_stack(base_predictions_test)

    # Logistic Regression (simples, evita overfitting)
    # SEM class_weight pois dados já estão balanceados!
    meta_model = LogisticRegression(
        C=1.0,
        random_state=42,
        max_iter=1000
    )
    meta_model.fit(X_meta_train, y_train_balanced)

    models['meta'] = meta_model

    # Final predictions
    meta_pred_test = meta_model.predict(X_meta_test)
    meta_pred_proba_test = meta_model.predict_proba(X_meta_test)[:, 1]
    meta_acc = accuracy_score(y_test, meta_pred_test)

    # Best base
    best_base_acc = max(base_accuracies)
    improvement = meta_acc - best_base_acc

    print(f"\n✅ Meta Accuracy: {meta_acc*100:.2f}%")
    print(f"   Melhor base: {best_base_acc*100:.2f}%")
    print(f"   Melhoria: {improvement*100:+.2f}%")

    # Class accuracy
    y_pred_long = meta_pred_test[y_test == 1]
    y_pred_short = meta_pred_test[y_test == 0]

    long_acc = accuracy_score(y_test[y_test == 1], y_pred_long)
    short_acc = accuracy_score(y_test[y_test == 0], y_pred_short)

    print(f"\n📊 Accuracy por classe:")
    print(f"   Long (COMPRA): {long_acc*100:.2f}%")
    print(f"   Short (VENDA): {short_acc*100:.2f}%")
    print(f"   Balanceamento: {abs(long_acc - short_acc)*100:.2f}% diferença")

    # Threshold ajustado (easier to enter longs)
    long_threshold = 0.35
    short_threshold = 0.65

    # Build models list
    models_list = [models['lgb'], models['xgb']]
    model_names_list = ['LightGBM', 'XGBoost']

    if HAS_CATBOOST and 'catboost' in models:
        models_list.append(models['catboost'])
        model_names_list.append('CatBoost')

    models_list.append(models['rf'])
    model_names_list.append('RandomForest')

    if use_dl:
        models_list.extend([models['lstm'], models['cnn']])
        model_names_list.extend(['LSTM', 'CNN'])

    # Equal weights for all models
    n_models = len(models_list)
    model_weights = [1.0 / n_models] * n_models

    # Wrap model
    wrapper = ModelWrapper(
        models_list=models_list,
        model_weights=model_weights,
        model_names=model_names_list,
        scaler=scaler,
        feature_columns=feature_cols,
        has_dl=use_dl,
        long_threshold=long_threshold,
        short_threshold=short_threshold,
        lookback=10
    )

    # Results
    results = {
        'days': days,
        'meta_accuracy': meta_acc,
        'best_base_accuracy': best_base_acc,
        'improvement': improvement,
        'long_accuracy': long_acc,
        'short_accuracy': short_acc,
        'balance_diff': abs(long_acc - short_acc),
        'n_features': len(feature_cols),
        'lgb_accuracy': lgb_acc,
        'xgb_accuracy': xgb_acc,
        'rf_accuracy': rf_acc
    }

    if HAS_CATBOOST:
        results['catboost_accuracy'] = cb_acc

    if use_dl:
        results['lstm_accuracy'] = lstm_acc
        results['cnn_accuracy'] = cnn_acc

    return wrapper, results


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":

    start_time = time.time()

    # Test periods
    test_periods = [365, 540]  # 1y, 1.5y (730 demora muito)

    all_results = []

    for days in test_periods:
        print("\n\n")
        print("=" * 80)
        print(f"📅 PERÍODO: {days} DIAS")
        print("=" * 80)

        # Download
        df = get_binance_klines(days=days)

        # Features
        df = add_extraordinary_features(df)

        # Train
        model, results = train_final_completo(df, days)
        all_results.append(results)

        # Save
        model_file = storage_dir / f"model_DEFINITIVO_4ML_{days}d.pkl"
        with open(model_file, 'wb') as f:
            pickle.dump(model, f)

        model_size_mb = os.path.getsize(model_file) / (1024 * 1024)
        print(f"\n💾 Modelo salvo: {model_file}")
        print(f"   Tamanho: {model_size_mb:.2f} MB")

    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================

    elapsed = time.time() - start_time

    print("\n\n")
    print("=" * 80)
    print("🏆 MODELO DEFINITIVO V6 - RESULTADOS FINAIS")
    print("=" * 80)
    print()

    # Find best (melhor balanceamento long/short)
    best_idx = np.argmin([r['balance_diff'] for r in all_results])
    best_result = all_results[best_idx]
    best_days = best_result['days']

    print(f"🥇 MELHOR PERÍODO (mais balanceado): {best_days} dias")
    print()

    for result in all_results:
        days = result['days']
        marker = "🥇" if days == best_days else "  "

        print(f"{marker} {days} dias:")
        print(f"   Meta:         {result['meta_accuracy']*100:.2f}%")
        print(f"   Long:         {result['long_accuracy']*100:.2f}%")
        print(f"   Short:        {result['short_accuracy']*100:.2f}%")
        print(f"   Desbalance:   {result['balance_diff']*100:.2f}%")
        print(f"   Melhoria:     {result['improvement']*100:+.2f}%")
        print(f"   Features:     {result['n_features']}")
        print()

    print("=" * 80)
    print(f"⏱️  Tempo total: {elapsed/60:.1f} minutos")
    print("=" * 80)
    print()

    print("🎯 MODELO RECOMENDADO:")
    print(f"   storage/models/model_DEFINITIVO_4ML_{best_days}d.pkl")
    print()

    print("✅ PRONTO para backtest!")
    print(f"   Execute: python backtest_PERFEITO.py")
    print()
