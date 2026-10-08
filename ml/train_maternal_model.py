import os
import json
import joblib
import pandas as pd
import numpy as np
import sklearn
from datetime import datetime
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    recall_score,
    precision_score,
    f1_score,
    accuracy_score
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(BASE_DIR, "Maternal Health Risk Data Set.csv")
MODEL_DIR = os.path.join(BASE_DIR, "ml")
MODEL_PATH = os.path.join(MODEL_DIR, "maternal_risk_model.joblib")
METADATA_PATH = os.path.join(MODEL_DIR, "model_metadata.json")

EXPECTED_FEATURES = ["Age", "SystolicBP", "DiastolicBP", "BS", "BodyTemp", "HeartRate"]
TARGET_COL = "RiskLevel"

LABEL_MAPPING = {
    "low risk": "Low Risk",
    "mid risk": "Medium Risk",
    "high risk": "High Risk"
}

def train_and_evaluate(dataset_csv_path=DATASET_PATH, force_retrain=False):
    print(f"Loading dataset from: {dataset_csv_path}")
    if not os.path.exists(dataset_csv_path):
        raise FileNotFoundError(f"Dataset file not found at {dataset_csv_path}")
    
    df = pd.read_csv(dataset_csv_path)
    print(f"Dataset shape: {df.shape}")
    
    # 1. Schema Validation
    missing_cols = [c for c in EXPECTED_FEATURES if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Dataset is missing required features: {missing_cols}")
    if TARGET_COL not in df.columns:
        raise ValueError(f"Dataset is missing target column: {TARGET_COL}")
    
    # Drop any unexpected columns or null values
    df_clean = df[EXPECTED_FEATURES + [TARGET_COL]].dropna()
    print(f"Cleaned records count: {len(df_clean)}")
    
    # 2. Normalize Target
    df_clean[TARGET_COL] = df_clean[TARGET_COL].astype(str).str.strip().str.lower().map(LABEL_MAPPING)
    if df_clean[TARGET_COL].isnull().any():
        unknown_labels = df[~df[TARGET_COL].astype(str).str.strip().str.lower().isin(LABEL_MAPPING.keys())][TARGET_COL].unique()
        raise ValueError(f"Unexpected target labels found: {unknown_labels}")
    
    X = df_clean[EXPECTED_FEATURES]
    y = df_clean[TARGET_COL]
    
    class_order = ["Low Risk", "Medium Risk", "High Risk"]
    hr_idx = class_order.index("High Risk")
    class_distribution = y.value_counts()[class_order].to_dict()
    print("Class distribution:", class_distribution)
    
    # 3. Stratified Split (80% train, 20% test, reproducible random_state=42)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.20,
        random_state=42,
        stratify=y
    )
    
    print(f"Train size: {len(X_train)}, Test size: {len(X_test)}")
    
    # 4. Compare Candidate Models with Recall as Primary Selection Criterion
    candidate_pipelines = {
        "GradientBoostingClassifier": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42))
        ]),
        "RandomForestClassifier": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, class_weight="balanced"))
        ]),
        "LogisticRegression": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced"))
        ])
    }
    
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    candidate_evaluations = {}
    
    print("\n--- Evaluating Candidate Classification Models (5-Fold CV on Train Set) ---")
    for name, pipeline in candidate_pipelines.items():
        hr_recalls, macro_recalls, macro_f1s, macro_precs, accuracies = [], [], [], [], []
        
        for tr_idx, val_idx in skf.split(X_train, y_train):
            X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
            y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]
            
            pipeline.fit(X_tr, y_tr)
            val_pred = pipeline.predict(X_val)
            
            rec_per_cls = recall_score(y_val, val_pred, average=None, labels=class_order)
            hr_recalls.append(rec_per_cls[hr_idx])
            macro_recalls.append(recall_score(y_val, val_pred, average="macro", labels=class_order))
            macro_f1s.append(f1_score(y_val, val_pred, average="macro", labels=class_order))
            macro_precs.append(precision_score(y_val, val_pred, average="macro", labels=class_order))
            accuracies.append(accuracy_score(y_val, val_pred))
            
        candidate_evaluations[name] = {
            "cv_high_risk_recall": float(np.mean(hr_recalls)),
            "cv_macro_recall": float(np.mean(macro_recalls)),
            "cv_macro_f1": float(np.mean(macro_f1s)),
            "cv_macro_precision": float(np.mean(macro_precs)),
            "cv_accuracy": float(np.mean(accuracies))
        }
        
        print(f"Candidate: {name}")
        print(f"  CV High-Risk Recall: {candidate_evaluations[name]['cv_high_risk_recall']*100:.2f}%")
        print(f"  CV Macro Recall:     {candidate_evaluations[name]['cv_macro_recall']*100:.2f}% | F1: {candidate_evaluations[name]['cv_macro_f1']*100:.2f}% | Acc: {candidate_evaluations[name]['cv_accuracy']*100:.2f}%")
    
    # Model Selection: Primary = High-Risk Recall, Secondary = Macro Recall, Macro F1, Macro Precision, Accuracy
    # Strictly selected using cross-validation on 80% training data without manual hardcoding
    best_model_name = max(
        candidate_evaluations,
        key=lambda name: (
            candidate_evaluations[name]["cv_high_risk_recall"],
            candidate_evaluations[name]["cv_macro_recall"],
            candidate_evaluations[name]["cv_macro_f1"],
            candidate_evaluations[name]["cv_macro_precision"],
            candidate_evaluations[name]["cv_accuracy"]
        )
    )
    print(f"\nModel Selected by Cross-Validation (High-Risk Recall Prioritized): {best_model_name}")
    print(f"  CV High-Risk Recall:    {candidate_evaluations[best_model_name]['cv_high_risk_recall']*100:.2f}%")
    print(f"  CV Macro Recall:        {candidate_evaluations[best_model_name]['cv_macro_recall']*100:.2f}%")
    print(f"  CV Macro F1:            {candidate_evaluations[best_model_name]['cv_macro_f1']*100:.2f}%")
    print(f"  CV Macro Precision:     {candidate_evaluations[best_model_name]['cv_macro_precision']*100:.2f}%")
    print(f"  CV Accuracy:            {candidate_evaluations[best_model_name]['cv_accuracy']*100:.2f}%")

    # Fit the genuinely selected model on the 80% training set
    selected_pipeline = candidate_pipelines[best_model_name]
    selected_pipeline.fit(X_train, y_train)
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(selected_pipeline, MODEL_PATH)
    print(f"Saved production model artifact ({best_model_name}) to: {MODEL_PATH}")
    
    # 5. Evaluate on Training and Held-out Test Sets
    y_train_pred = selected_pipeline.predict(X_train)
    train_accuracy = float(accuracy_score(y_train, y_train_pred))
    train_recall_macro = float(recall_score(y_train, y_train_pred, average="macro", labels=class_order))
    train_precision_macro = float(precision_score(y_train, y_train_pred, average="macro", labels=class_order))
    train_f1_macro = float(f1_score(y_train, y_train_pred, average="macro", labels=class_order))
    train_rec_per_cls = recall_score(y_train, y_train_pred, average=None, labels=class_order)
    train_hr_recall = float(train_rec_per_cls[hr_idx])

    y_pred = selected_pipeline.predict(X_test)
    test_accuracy = float(accuracy_score(y_test, y_pred))
    test_recall_macro = float(recall_score(y_test, y_pred, average="macro", labels=class_order))
    test_recall_weighted = float(recall_score(y_test, y_pred, average="weighted", labels=class_order))
    test_precision_macro = float(precision_score(y_test, y_pred, average="macro", labels=class_order))
    test_precision_weighted = float(precision_score(y_test, y_pred, average="weighted", labels=class_order))
    test_f1_macro = float(f1_score(y_test, y_pred, average="macro", labels=class_order))
    test_f1_weighted = float(f1_score(y_test, y_pred, average="weighted", labels=class_order))
    
    # Per-class metrics
    per_class_recall = recall_score(y_test, y_pred, average=None, labels=class_order)
    per_class_precision = precision_score(y_test, y_pred, average=None, labels=class_order)
    per_class_f1 = f1_score(y_test, y_pred, average=None, labels=class_order)
    
    class_metrics = {}
    for i, cls_name in enumerate(class_order):
        class_metrics[cls_name] = {
            "recall": float(per_class_recall[i]),
            "precision": float(per_class_precision[i]),
            "f1": float(per_class_f1[i])
        }
    
    hr_test_recall = class_metrics["High Risk"]["recall"]
    hr_test_precision = class_metrics["High Risk"]["precision"]
    hr_test_f1 = class_metrics["High Risk"]["f1"]

    cm = confusion_matrix(y_test, y_pred, labels=class_order).tolist()
    clf_report_dict = classification_report(y_test, y_pred, labels=class_order, output_dict=True)
    
    # Print formatted model report prioritizing recall per Section 2
    print("\n" + "=" * 68)
    print("         MEDICONNECT - MODEL EVALUATION REPORT (RECALL-FOCUSED)")
    print("=" * 68)
    print("PRIMARY METRIC")
    print(f"High-Risk Recall:       {hr_test_recall * 100:.2f}%\n")
    print("SECONDARY METRICS")
    print(f"Macro Recall:           {test_recall_macro * 100:.2f}%")
    print(f"Macro Precision:        {test_precision_macro * 100:.2f}%")
    print(f"Macro F1:               {test_f1_macro * 100:.2f}%")
    print(f"Accuracy:               {test_accuracy * 100:.2f}%\n")
    print("HIGH-RISK CLASS")
    print(f"Precision:              {hr_test_precision * 100:.2f}%")
    print(f"Recall:                 {hr_test_recall * 100:.2f}%")
    print(f"F1:                     {hr_test_f1 * 100:.2f}%\n")
    print("COMPLETE PER-CLASS TEST RESULTS")
    print(f"{'Class':<15} | {'Recall':<10} | {'Precision':<10} | {'F1-Score':<10}")
    print("-" * 55)
    for cls in class_order:
        m = class_metrics[cls]
        print(f"{cls:<15} | {m['recall']*100:>8.2f}% | {m['precision']*100:>8.2f}% | {m['f1']*100:>8.2f}%")
    print("-" * 55)
    
    print("\nHIGH-RISK RECALL EXPLANATION:")
    print(f"The model achieved {hr_test_recall*100:.2f}% recall for the High Risk class,")
    print("meaning it correctly identified most actual High Risk cases in the held-out test set.")
    
    print(f"\nConfusion Matrix (Labels: {class_order}):\n{np.array(cm)}")
    print("=" * 68)
    
    # 6. Feature importances if available
    feature_importances = {}
    if hasattr(selected_pipeline.named_steps["clf"], "feature_importances_"):
        fi = selected_pipeline.named_steps["clf"].feature_importances_
        feature_importances = {feat: float(fi[idx]) for idx, feat in enumerate(EXPECTED_FEATURES)}
    
    # 7. Save Model Metadata
    metadata = {
        "model_version": "v1.0.0",
        "algorithm": best_model_name,
        "dataset_name": os.path.basename(dataset_csv_path),
        "total_records": len(df_clean),
        "train_records": len(X_train),
        "test_records": len(X_test),
        "train_test_split": "80/20 Stratified",
        "random_state": 42,
        "features": EXPECTED_FEATURES,
        "target": TARGET_COL,
        "classes": class_order,
        "class_distribution": class_distribution,
        "primary_metric": "High-Risk Recall",
        "training_metrics": {
            "high_risk_recall": round(train_hr_recall, 4),
            "recall_macro": round(train_recall_macro, 4),
            "precision_macro": round(train_precision_macro, 4),
            "f1_macro": round(train_f1_macro, 4),
            "accuracy": round(train_accuracy, 4)
        },
        "evaluation_metrics": {
            "primary_metric": "High-Risk Recall",
            "high_risk_recall": round(hr_test_recall, 4),
            "high_risk_precision": round(hr_test_precision, 4),
            "high_risk_f1": round(hr_test_f1, 4),
            "recall_macro": round(test_recall_macro, 4),
            "recall_weighted": round(test_recall_weighted, 4),
            "precision_macro": round(test_precision_macro, 4),
            "precision_weighted": round(test_precision_weighted, 4),
            "f1_macro": round(test_f1_macro, 4),
            "f1_weighted": round(test_f1_weighted, 4),
            "accuracy": round(test_accuracy, 4),
            "per_class": {k: {m: round(v, 4) for m, v in vals.items()} for k, vals in class_metrics.items()}
        },
        "confusion_matrix": {
            "labels": class_order,
            "matrix": cm
        },
        "classification_report": clf_report_dict,
        "candidate_models_cv": candidate_evaluations,
        "feature_importances": feature_importances,
        "scikit_learn_version": sklearn.__version__,
        "trained_at": datetime.now().isoformat(),
        "explanation": f"High-Risk Recall is used as the primary evaluation metric to prioritize detection of high-risk cases. The model achieved {hr_test_recall*100:.2f}% recall for the High Risk class on the held-out test set.",
        "disclaimer": "Decision-support prediction only. This is not a medical diagnosis."
    }
    
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Model metadata saved to: {METADATA_PATH}")
    
    return metadata

if __name__ == "__main__":
    train_and_evaluate()
