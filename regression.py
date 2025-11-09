from sklearn.linear_model import LogisticRegressionCV, LassoCV, RidgeCV
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.model_selection import RandomizedSearchCV
from scipy.stats import randint, uniform
from sklearn.preprocessing import StandardScaler
import numpy as np
import pandas as pd
import re, json

# -----------------------------
# STEP 1: Load and preprocess
# -----------------------------
df = pd.read_csv('team_aggregated_stats_labeled.csv')
df = df[~((df['Team'] == 'CHA') & (df['Season'] == '2003-04'))]
X = df.drop(columns=['Team', 'Season', 'playoffs'])
y = df['playoffs']


# choose best feature variant per base feature using signed Spearman correlation
base_features = set()
for col in X.columns:
    match = re.match(r'^(.*)_(highest|top2_avg|weighted)$', col)
    if match:
        base_features.add(match.group(1))

print(base_features)
feature_type_selection = {}
for feature in base_features:
    highest_col = f'{feature}_highest'
    top2_avg_col = f'{feature}_top2_avg'
    weighted_col = f'{feature}_weighted'
    corr_highest = X[highest_col].corr(y, method='spearman')
    corr_top2_avg = X[top2_avg_col].corr(y, method='spearman')
    corr_weighted = X[weighted_col].corr(y, method='spearman')
    corrs = {'highest': corr_highest, 'top2_avg': corr_top2_avg, 'weighted': corr_weighted}
    print(corrs)    
    best_type = max(corrs, key=corrs.get)
    feature_type_selection[feature] = best_type

with open("feature_correlations.json", "w") as f:
    json.dump(feature_type_selection, f, indent=4)

features = [f"{key}_{value}" for key, value in feature_type_selection.items()]
X_feature_selected = X[features]

# -----------------------------
# STEP 2: Standardize
# -----------------------------
feature_names = X_feature_selected.columns 
scaler = StandardScaler(with_mean=True, with_std=True)
X_feature_selected = scaler.fit_transform(X_feature_selected)

# -----------------------------
# STEP 3: Models
# -----------------------------
def normalize_signed(arr):
    return arr / np.sum(np.abs(arr))

# Elastic Net Logistic Regression
l1_ratios = np.linspace(0.1, 0.9, 9)
Cs = np.logspace(-4, 4, 20)
log_reg = LogisticRegressionCV(
    penalty='elasticnet',
    solver='saga',
    l1_ratios=l1_ratios,
    Cs=Cs,
    cv=5,
    scoring='roc_auc',
    max_iter=20000,
    n_jobs=-1,
    random_state=42
)
log_reg.fit(X_feature_selected, y)
elastic_importance = normalize_signed(log_reg.coef_.mean(axis=0))

# Lasso Regression (L1)
alphas_lasso = np.logspace(-4, 4, 20)
lasso = LassoCV(
    cv=5,
    alphas=alphas_lasso,
    max_iter=20000,
    n_jobs=-1,
    random_state=42
)
lasso.fit(X_feature_selected, y)
lasso_importance = normalize_signed(lasso.coef_)

print("\nBest Lasso (L1) Parameters:")
print(f"Best alpha: {lasso.alpha_}")
print(f"Best score (R²): {lasso.score(X_feature_selected, y):.4f}")

# Ridge Regression (L2)
alphas = np.logspace(-4, 4, 20)
ridge = RidgeCV(
    alphas=alphas,
    cv=5,
    scoring='r2'
)
ridge.fit(X_feature_selected, y)
ridge_importance = normalize_signed(ridge.coef_)

print("\nBest Ridge (L2) Parameters:")
print(f"Best alpha: {ridge.alpha_}")
print(f"Best score (R²): {ridge.score(X_feature_selected, y):.4f}")

# Random Forest (tuned via RandomizedSearchCV using ROC AUC)
rf_base = RandomForestClassifier(random_state=42, n_jobs=-1)
rf_param_dist = {
    'n_estimators': [200, 500, 800],
    'max_depth': [3, 5, 8, None],
    'min_samples_split': randint(2, 11),
    'min_samples_leaf': randint(1, 6),
    'max_features': ['sqrt', 'log2', 0.5]
}
rf_search = RandomizedSearchCV(
    rf_base,
    param_distributions=rf_param_dist,
    n_iter=30,
    scoring='roc_auc',
    cv=5,
    random_state=42,
    n_jobs=-1,
    refit=True
)
rf_search.fit(X_feature_selected, y)
rf_best = rf_search.best_estimator_
print("\nBest RandomForest params:", rf_search.best_params_)
print(f"Best RandomForest ROC AUC (CV): {rf_search.best_score_:.4f}")
rf_importance = normalize_signed(rf_best.feature_importances_)

# XGBoost (tuned via RandomizedSearchCV using ROC AUC)
xgb_base = XGBClassifier(random_state=42, n_jobs=-1, use_label_encoder=False, eval_metric='logloss')
xgb_param_dist = {
    'n_estimators': [200, 500, 800],
    'max_depth': randint(2, 8),
    'learning_rate': uniform(0.01, 0.29),
    'subsample': uniform(0.6, 0.4),
    'colsample_bytree': uniform(0.6, 0.4),
    'gamma': uniform(0, 5)
}
xgb_search = RandomizedSearchCV(
    xgb_base,
    param_distributions=xgb_param_dist,
    n_iter=40,
    scoring='roc_auc',
    cv=5,
    random_state=42,
    n_jobs=-1,
    refit=True
)
xgb_search.fit(X_feature_selected, y)
xgb_best = xgb_search.best_estimator_
print("\nBest XGBoost params:", xgb_search.best_params_)
print(f"Best XGBoost ROC AUC (CV): {xgb_search.best_score_:.4f}")
xgb_importance = normalize_signed(xgb_best.feature_importances_)

# -----------------------------
# STEP 4: Combine and rank
# -----------------------------
importance_df = pd.DataFrame({
    'feature': feature_names,
    'elastic_net': elastic_importance,
    'lasso': lasso_importance,
    'ridge': ridge_importance,
    'random_forest': rf_importance,
    'xgboost': xgb_importance
})
importance_df['avg_importance'] = importance_df[['elastic_net', 'lasso', 'ridge', 'random_forest', 'xgboost']].mean(axis=1)
importance_df = importance_df.sort_values('avg_importance', ascending=False).reset_index(drop=True)

print("Normalized sum check:")
print(importance_df[['elastic_net', 'lasso', 'ridge', 'random_forest', 'xgboost']].apply(lambda x: np.sum(np.abs(x)), axis=0))

print("\nFeatures by average signed importance:")
print(importance_df)
