#!/usr/bin/env python3
"""
Script para adicionar o método _predict_from_wrapper ao arquivo 1.py
"""

def fix_file():
    filepath = '1.py'

    print("🔧 Corrigindo arquivo 1.py...")

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Código do método _predict_from_wrapper
    wrapper_method = '''    def _predict_from_wrapper(self, X):
        """Make predictions from ModelWrapper ensemble."""
        # ModelWrapper structure:
        # - models_list: list of models
        # - model_weights: weights for each model
        # - scaler: scaler for normalization (optional)

        try:
            # Apply scaler if exists
            if hasattr(self.model, 'scaler') and self.model.scaler is not None:
                X_scaled = self.model.scaler.transform(X)
            else:
                X_scaled = X.values if hasattr(X, 'values') else X

            # Get predictions from each model
            if hasattr(self.model, 'models_list') and self.model.models_list:
                predictions = []

                for i, model in enumerate(self.model.models_list):
                    try:
                        # Try predict_proba first (for classifiers)
                        if hasattr(model, 'predict_proba'):
                            pred = model.predict_proba(X_scaled)
                            # Get probability of class 1
                            if len(pred.shape) > 1 and pred.shape[1] > 1:
                                pred = pred[:, 1]
                        # Fall back to predict
                        elif hasattr(model, 'predict'):
                            pred = model.predict(X_scaled)
                        else:
                            logger.warning(f"   ⚠️  Model {i} has no predict method, skipping")
                            continue

                        predictions.append(pred)
                    except Exception as e:
                        logger.warning(f"   ⚠️  Error predicting with model {i}: {str(e)[:50]}")
                        continue

                if not predictions:
                    raise ValueError("No model could make predictions")

                # Combine predictions with weights if available
                if hasattr(self.model, 'model_weights') and self.model.model_weights:
                    # Weighted average
                    weights = np.array(self.model.model_weights[:len(predictions)])
                    weights = weights / weights.sum()  # Normalize

                    final_pred = np.zeros_like(predictions[0])
                    for pred, weight in zip(predictions, weights):
                        final_pred += pred * weight
                else:
                    # Simple average
                    final_pred = np.mean(predictions, axis=0)

                return final_pred
            else:
                raise ValueError("ModelWrapper has no models_list")

        except Exception as e:
            logger.error(f"   ❌ Error in _predict_from_wrapper: {str(e)}")
            raise

'''

    # Encontrar onde inserir (após o método _add_missing_features)
    insert_index = None
    for i, line in enumerate(lines):
        if 'return df' in line and i > 750 and i < 765:
            # Procura por "return df" depois de _add_missing_features
            # Verifica se é o return certo olhando algumas linhas antes
            if any('missing' in lines[j].lower() for j in range(max(0, i-10), i)):
                insert_index = i + 1
                break

    if insert_index is None:
        print("❌ Não consegui encontrar onde inserir. Procurando 'def backtest_with_confidence'...")
        for i, line in enumerate(lines):
            if 'def backtest_with_confidence' in line:
                insert_index = i
                print(f"✅ Encontrado na linha {i}, vou inserir antes")
                break

    if insert_index is None:
        print("❌ Erro: não consegui encontrar onde inserir o código")
        return False

    print(f"📍 Inserindo método na linha {insert_index + 1}")

    # Inserir o método
    lines.insert(insert_index, '\n')
    lines.insert(insert_index + 1, wrapper_method)

    # Agora atualizar a parte do backtest_with_confidence para usar o método
    for i, line in enumerate(lines):
        if 'except AttributeError:' in line and 'predict' in lines[i-1]:
            # Encontrou o except certo
            # Procurar pela linha que tem "raise ValueError"
            for j in range(i, min(i+10, len(lines))):
                if 'raise ValueError("Model has no predict' in lines[j]:
                    # Substituir por código com verificação de models_list
                    new_code = '''            # If model doesn't have predict, maybe it's an ensemble wrapper
            if hasattr(self.model, '__call__'):
                ml_probs = self.model(X)
            elif hasattr(self.model, 'models_list'):
                # ModelWrapper with ensemble
                logger.info(f"   🔄 Using ensemble prediction from ModelWrapper")
                ml_probs = self._predict_from_wrapper(X)
            else:
                raise ValueError("Model has no predict() or __call__() method")
'''
                    # Remover linhas antigas
                    # Contar quantas linhas remover
                    start_comment = i + 1
                    end_raise = j + 1

                    # Substituir
                    del lines[start_comment:end_raise]
                    lines.insert(start_comment, new_code)
                    print(f"✅ Atualizado verificação de models_list na linha {i}")
                    break
            break

    # Salvar arquivo
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"✅ Arquivo corrigido!")
    print(f"📊 Total de linhas: {len(lines)}")

    return True

if __name__ == '__main__':
    success = fix_file()
    if success:
        print("\n🎉 Correção aplicada com sucesso!")
        print("🔄 Rode novamente: python check_version.py")
    else:
        print("\n❌ Erro ao aplicar correção")
