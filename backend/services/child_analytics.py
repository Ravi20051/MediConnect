import os
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHILD_DATASET_PATH = os.path.join(BASE_DIR, "Child Immunization Dataset.xls")
VARIABLES_PATH = os.path.join(BASE_DIR, "Varibles of Child Immunization Dataset.xlsx")

class ChildAnalyticsService:
    def __init__(self):
        self.df = None
        self.dict_df = None
        self.load_datasets()

    def load_datasets(self):
        if os.path.exists(CHILD_DATASET_PATH):
            try:
                self.df = pd.read_excel(CHILD_DATASET_PATH, sheet_name=0)
            except Exception as e:
                print(f"Error loading child immunization dataset: {e}")

        if os.path.exists(VARIABLES_PATH):
            try:
                self.dict_df = pd.read_excel(VARIABLES_PATH, sheet_name=0)
            except Exception as e:
                print(f"Error loading variables definition: {e}")

    def get_coverage_summary(self):
        if self.df is None:
            self.load_datasets()
            if self.df is None:
                return {"error": "Child immunization dataset not available"}

        total_districts = len(self.df)
        total_states = self.df["STATE"].nunique() if "STATE" in self.df.columns else 0
        total_pop = int(self.df["POPULATION"].sum()) if "POPULATION" in self.df.columns else 0

        # Totals of key immunization columns
        bcg_total = float(self.df["BCG"].sum()) if "BCG" in self.df.columns else 0
        penta1_total = float(self.df["PENTA_1"].sum()) if "PENTA_1" in self.df.columns else 0
        penta3_total = float(self.df["PENTA_3"].sum()) if "PENTA_3" in self.df.columns else 0
        measles1_total = float(self.df["MEAS_1"].sum()) if "MEAS_1" in self.df.columns else 0
        fully_immunized_total = float(self.df["T_FI_9_11"].sum()) if "T_FI_9_11" in self.df.columns else 0

        # National dropout indicator (Penta1 to Penta3 dropout percentage)
        penta_dropout = 0.0
        if penta1_total > 0:
            penta_dropout = round(((penta1_total - penta3_total) / penta1_total) * 100, 2)

        # State level aggregated summary
        state_summary = []
        if "STATE" in self.df.columns:
            state_grp = self.df.groupby("STATE").agg({
                "DISTRICT": "count",
                "POPULATION": "sum",
                "BCG": "sum",
                "PENTA_1": "sum",
                "PENTA_3": "sum",
                "MEAS_1": "sum",
                "T_FI_9_11": "sum",
                "IS_ASHA": "sum"
            }).reset_index()

            state_grp = state_grp.sort_values(by="T_FI_9_11", ascending=False)
            for _, row in state_grp.head(15).iterrows():
                p1 = row["PENTA_1"]
                p3 = row["PENTA_3"]
                drop = round(((p1 - p3) / p1) * 100, 2) if p1 > 0 else 0.0
                state_summary.append({
                    "state": str(row["STATE"]),
                    "districts": int(row["DISTRICT"]),
                    "population": int(row["POPULATION"]),
                    "bcg": int(row["BCG"]),
                    "penta_1": int(row["PENTA_1"]),
                    "penta_3": int(row["PENTA_3"]),
                    "measles_1": int(row["MEAS_1"]),
                    "fully_immunized": int(row["T_FI_9_11"]),
                    "asha_sessions": int(row["IS_ASHA"]),
                    "dropout_pct": max(0.0, drop)
                })

        # Variables dictionary
        data_dictionary = []
        if self.dict_df is not None:
            for _, row in self.dict_df.iterrows():
                data_dictionary.append({
                    "code": str(row.get("New Name", "")),
                    "title": str(row.get("New Variable Name", "")),
                    "description": str(row.get("Old Variable Name", ""))
                })

        return {
            "dataset_info": {
                "source_file": "Child Immunization Dataset.xls",
                "dictionary_file": "Varibles of Child Immunization Dataset.xlsx",
                "scope": "Aggregate District & State Level Immunization Coverage across India",
                "honest_usage_note": "This dataset provides macro-level coverage benchmarking and dropout analytics. Per project requirements, this aggregate data is NOT used for individual-child ML predictions.",
                "total_districts": total_districts,
                "total_states": total_states,
                "total_population_covered": total_pop
            },
            "aggregate_metrics": {
                "total_bcg_administered": int(bcg_total),
                "total_penta1": int(penta1_total),
                "total_penta3": int(penta3_total),
                "total_measles1": int(measles1_total),
                "total_fully_immunized_infants": int(fully_immunized_total),
                "penta_dropout_rate_pct": penta_dropout
            },
            "top_states": state_summary,
            "data_dictionary": data_dictionary[:12]
        }

child_analytics_service = ChildAnalyticsService()
