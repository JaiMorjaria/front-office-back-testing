from sklearn.linear_model import LogisticRegressionCV
from sklearn.model_selection import StratifiedGroupKFold, cross_validate
from sklearn.metrics import roc_auc_score, classification_report
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.inspection import permutation_importance
import numpy as np
import pandas as pd

# ------------------------------------------------------------
# Two different labeled datasets
#   • pretenders_stats_labeled.csv   (has `playoffs` column)
#   • contenders_stats_labeled.csv   (has `conf_finals` column)
# ------------------------------------------------------------
datasets = {
    "playoffs": ("pretenders_stats_labeled.csv", "playoffs"),
    "conf_finals": ("contenders_stats_labeled.csv", "conf_finals")
}

for label_name, (filename, target_col) in datasets.items():
    print("\n" + "="*60)
    print(f"Running model for: {label_name.upper()}")
    print("="*60)

    # Load per-target dataset
    df = pd.read_csv(filename)
    df = df[~((df['Team'] == 'CHA') & (df['Season'] == '2003-04'))]

    # -----------------------------
    # Setup X and y
    # -----------------------------
    # Drop only what must be dropped, not columns that may not exist
    drop_cols = [c for c in ['Team', 'Season'] if c in df.columns]
    X = df.drop(columns=drop_cols + [target_col])
    y = df[target_col]
    groups = df['Season']

    # -----------------------------
    # Define pipeline
    # -----------------------------
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('clf', LogisticRegressionCV(
            penalty='elasticnet',
            solver='saga',
            l1_ratios=np.linspace(0.1, 0.9, 9),
            Cs=np.logspace(-2, 2, 10),
            cv=5,
            scoring='roc_auc',
            max_iter=20000,
            n_jobs=-1,
            random_state=42
        ))
    ])

    # Season-aware CV
    cv = StratifiedGroupKFold(n_splits=5)
    cv_results = cross_validate(
        pipeline, X, y, groups=groups,
        cv=cv, scoring='roc_auc',
        return_estimator=True
    )

    print(f"Mean ROC AUC ({label_name}): {cv_results['test_score'].mean():.4f}")

    # Fit final model
    pipeline.fit(X, y)

    # -----------------------------
    # Permutation Importance
    # -----------------------------
    result = permutation_importance(
        pipeline, X, y,
        n_repeats=10,
        random_state=42,
        n_jobs=-1,
        scoring='roc_auc'
    )

    perm_importance_df = pd.DataFrame({
        'feature': X.columns,
        'importance_mean': result.importances_mean,
        'importance_std': result.importances_std
    }).sort_values('importance_mean', ascending=False)

    perm_importance_df.to_csv(
        f'perm_importance_{label_name}.csv',
        index=False
    )

    # -----------------------------
    # Coefficient-Based Importance
    # -----------------------------
    final_model = pipeline.named_steps['clf']

    coefs = pd.DataFrame({
        'feature': X.columns,
        'coefficient': final_model.coef_[0],
        'abs_coefficient': np.abs(final_model.coef_[0])
    }).sort_values('abs_coefficient', ascending=False)

    coefs.to_csv(
        f'feature_importance_elastic_net_{label_name}.csv',
        index=False
    )

    print("\nTOP 10 POSITIVE FEATURES")
    print(coefs.sort_values('coefficient', ascending=False)
              .head(10)[['feature', 'coefficient']]
              .to_string(index=False))

    print("\nTOP 10 NEGATIVE FEATURES")
    print(coefs.sort_values('coefficient', ascending=True)
              .head(10)[['feature', 'coefficient']]
              .to_string(index=False))
