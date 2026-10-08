import os
import joblib
import pandas as pd
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(BASE_DIR, "ml", "maternal_risk_model.joblib")
METADATA_PATH = os.path.join(BASE_DIR, "ml", "model_metadata.json")

EXPECTED_FEATURES = ["Age", "SystolicBP", "DiastolicBP", "BS", "BodyTemp", "HeartRate"]

class MaternalService:
    def __init__(self):
        self.model = None
        self.metadata = None
        self.load_model()

    def load_model(self):
        if os.path.exists(MODEL_PATH):
            self.model = joblib.load(MODEL_PATH)
        if os.path.exists(METADATA_PATH):
            with open(METADATA_PATH, "r") as f:
                self.metadata = json.load(f)

    def predict_risk(self, age: float, systolic_bp: float, diastolic_bp: float, bs: float, body_temp: float, heart_rate: float) -> dict:
        if self.model is None:
            self.load_model()
            if self.model is None:
                raise RuntimeError("Maternal ML model artifact not found. Please train model first.")

        # Input dataframe with exact features
        input_data = pd.DataFrame([{
            "Age": float(age),
            "SystolicBP": float(systolic_bp),
            "DiastolicBP": float(diastolic_bp),
            "BS": float(bs),
            "BodyTemp": float(body_temp),
            "HeartRate": float(heart_rate)
        }])

        pred_label = self.model.predict(input_data)[0]
        probabilities = self.model.predict_proba(input_data)[0]
        classes = self.model.classes_

        prob_dict = {cls_name: round(float(prob), 4) for cls_name, prob in zip(classes, probabilities)}
        predicted_prob = prob_dict.get(pred_label, 0.0)

        # Action guidance per established clinical review procedures (Decision-Support Only)
        if pred_label == "High Risk":
            action_guidance = "High-risk case identified. Review according to established clinical/referral procedures."
            alert_class = "danger"
            requires_referral = True
        elif pred_label == "Medium Risk":
            action_guidance = "Medium-risk prediction. Review and follow according to established procedures."
            alert_class = "warning"
            requires_referral = False
        else:
            action_guidance = "Low-risk prediction. Continue routine follow-up according to established procedures."
            alert_class = "success"
            requires_referral = False

        return {
            "risk_level": pred_label,
            "predicted_class_probability": predicted_prob,
            "confidence": predicted_prob,  # Backward compatibility alias
            "probabilities": prob_dict,
            "model_version": self.metadata.get("model_version", "v1.0.0") if self.metadata else "v1.0.0",
            "algorithm": self.metadata.get("algorithm", "RandomForestClassifier") if self.metadata else "RandomForestClassifier",
            "action_guidance": action_guidance,
            "requires_referral": requires_referral,
            "alert_class": alert_class,
            "input_values": {
                "Age": age,
                "SystolicBP": systolic_bp,
                "DiastolicBP": diastolic_bp,
                "BS": bs,
                "BodyTemp": body_temp,
                "HeartRate": heart_rate
            },
            "disclaimer": "Decision-support prediction only. This is not a medical diagnosis.",
            "evaluation_note": "High-Risk Recall is used as the primary evaluation metric to prioritize detection of high-risk cases."
        }

maternal_service = MaternalService()
