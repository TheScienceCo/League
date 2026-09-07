"""Machine learning services.

Estimators are constructed through `registry.make_classifier` so the backend can
move from scikit-learn's gradient boosting to XGBoost (or a PyTorch model) by
changing a factory rather than the call sites.
"""
