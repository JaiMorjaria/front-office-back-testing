from sklearn.linear_model import LogisticRegressionCV
from sklearn.ensemble import RandomForestClassifier
import numpy as np
import pandas as pd
import re
import json

df = pd.read_csv('team_aggregated_stats_labeled.csv')
df = df.dropna()
X = df.drop(columns=['Team', 'Season', 'conf_finals_and_up'])
y = df['conf_finals_and_up']

base_features = set()
for col in X.columns:
    match = re.match(r'^(.*)_(highest|top2_avg|weighted)$', col)
    if match:
        base_features.add(match.group(1))

# get feature type with highest spearman correlation between highest, top2_avg, weighted
feature_type_selection = {}
for feature in base_features:
    highest_col = f'{feature}_highest'
    top2_avg_col = f'{feature}_top2_avg'
    weighted_col = f'{feature}_weighted'
    
    corr_highest = X[highest_col].corr(y, method='spearman')
    corr_top2_avg = X[top2_avg_col].corr(y, method='spearman')
    corr_weighted = X[weighted_col].corr(y, method='spearman')
    
    corrs = {
        'highest': abs(corr_highest),
        'top2_avg': abs(corr_top2_avg),
        'weighted': abs(corr_weighted)
    }
    
    best_type = max(corrs, key=corrs.get)
    feature_type_selection[feature] = best_type

with open("feature_correlations.json", "w") as f:
    json.dump(feature_type_selection, f, indent=4)

features = [key + "_" + value for key, value in feature_type_selection.items()]
X_feature_selected = X[features]  

corr_matrix = X_feature_selected.corr().abs()



rf = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=15,
            class_weight='balanced',
            random_state=42,
            n_jobs=-1
        )
rf.fit(X_feature_selected, y)

n_prefilter = 30
importances = pd.Series(rf.feature_importances_, index=X_feature_selected.columns)
top_features = importances.nlargest(n_prefilter).index
X_filtered = X_feature_selected[top_features]

print(top_features)
# X_weighted = X.filter(regex='_weighted$')


# # -----------------------------
# # STEP 2: LogisticRegressionCV with ElasticNet
# # -----------------------------

# model = LogisticRegressionCV(
#     penalty='elasticnet',
#     solver='saga',
#     l1_ratios=[0.4, 0.5, 0.6],     # mostly sparse, slightly stable
#     Cs=20,                           # inverse regularization strengths
#     cv=10,
#     scoring='roc_auc',
#     max_iter=20000,                  # increase for convergence
# )

# model.fit(X_weighted, y)

# # # -----------------------------
# # # STEP 3: Extract features and rank by absolute coefficient
# # # -----------------------------
# coefs = model.coef_.flatten()
# selected_features = X_weighted.columns[coefs != 0]

# feature_importance = pd.Series(coefs[coefs != 0], index=selected_features)
# feature_importance = feature_importance.abs().sort_values(ascending=False)

# # Top 10 features
# top10_features = feature_importance.head(10)

# print("Selected features with nonzero coefficients:")
# print(feature_importance)
# print(sum(feature_importance.values))
# print("\nTop 10 features:")
# print(top10_features)
