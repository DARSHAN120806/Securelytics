# Model comparison (unseen test period, 555,719 transactions)

| Model | PR-AUC | ROC-AUC | Accuracy | Precision | Recall | F1 | False blocks | Missed fraud | Latency p50 |
|---|---|---|---|---|---|---|---|---|---|
| XGBoost **(default)** | 0.9776 | 0.9995 | 99.9523% | 94.21% | 93.38% | 0.9380 | 123 | 142 | 9.08 ms |
| HistGradientBoosting (scikit-learn) | 0.9751 | 0.9995 | 99.9534% | 94.99% | 92.82% | 0.9389 | 105 | 154 | 13.31 ms |
| LightGBM | 0.9742 | 0.9994 | 99.9494% | 94.38% | 92.40% | 0.9338 | 118 | 163 | 5.06 ms |
| CatBoost | 0.9683 | 0.9988 | 99.9451% | 93.07% | 92.68% | 0.9288 | 148 | 157 | 4.28 ms |
| Logistic regression (baseline) | 0.3248 | 0.9873 | 99.4875% | 39.98% | 65.36% | 0.4961 | 2105 | 743 | - |

Accuracy, precision, recall and F1 are at each model's BLOCK threshold.
Accuracy is shown for completeness but is misleading here: predicting 'legit' for everything already scores 99.6%. Compare models on PR-AUC, recall and false blocks.
