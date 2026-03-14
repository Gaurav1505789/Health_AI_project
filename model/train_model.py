import pickle
import re
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import MultiLabelBinarizer


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "model"


def _load_csv_with_fallback(primary_name, fallback_names):
    """Load CSV by primary name, then known fallback names if needed."""
    for name in [primary_name] + fallback_names:
        file_path = DATA_DIR / name
        if file_path.exists():
            print(f"Loaded {name}")
            return pd.read_csv(file_path)
    raise FileNotFoundError(f"Could not find {primary_name} in {DATA_DIR}")


def _find_column(df, candidates):
    """Find a column using case-insensitive and underscore/space-insensitive matching."""
    normalized_map = {}
    for col in df.columns:
        key = col.strip().lower().replace("_", " ")
        key = re.sub(r"\s+", " ", key)
        normalized_map[key] = col

    for candidate in candidates:
        key = candidate.strip().lower().replace("_", " ")
        key = re.sub(r"\s+", " ", key)
        if key in normalized_map:
            return normalized_map[key]

    raise KeyError(f"None of the columns were found: {candidates}")


def _normalize_text(value):
    """Lowercase, trim, and remove punctuation for stable key matching."""
    text = str(value).strip().lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _split_csv_list(value):
    """Split a comma-separated field into cleaned string values."""
    if pd.isna(value):
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def build_training_dataset():
    """Build normalized symptom -> disease training rows from symptom dataset only."""
    symptom_df = _load_csv_with_fallback(
        "Indian-Healthcare-Symptom-Disease-Dataset.csv",
        ["Indian-Healthcare-Symptom-Disease-Dataset - Sheet1 (2).csv"],
    )

    symptom_disease_col = _find_column(symptom_df, ["Possible Diseases"])
    symptom_col = _find_column(symptom_df, ["Symptom"])

    # Map symptom dataset disease source to a unified disease field.
    symptom_pairs = symptom_df[[symptom_col, symptom_disease_col]].copy()
    symptom_pairs = symptom_pairs.rename(columns={symptom_col: "symptom", symptom_disease_col: "possible_diseases"})

    # Split comma-separated disease list and explode rows so each row has one disease.
    symptom_pairs["disease_candidates"] = symptom_pairs["possible_diseases"].apply(_split_csv_list)
    symptom_pairs = symptom_pairs.explode("disease_candidates")
    symptom_pairs = symptom_pairs.dropna(subset=["disease_candidates"])

    symptom_pairs["dataset_name"] = symptom_pairs["disease_candidates"].astype(str).str.strip()
    symptom_pairs["disease"] = symptom_pairs["dataset_name"].apply(_normalize_text)
    symptom_pairs["symptom"] = symptom_pairs["symptom"].apply(_normalize_text)

    training_df = (
        symptom_pairs.groupby("disease", as_index=False)
        .agg(
            symptom_list=("symptom", lambda values: sorted(set([v for v in values if v]))),
            dataset_name=("dataset_name", "first"),
        )
    )

    return training_df


def train_and_save():
    """Train model from symptom data and save model artifacts."""
    training_df = build_training_dataset()

    # Train the classifier only with symptom dataset pairs: symptoms -> disease.
    mlb = MultiLabelBinarizer()
    X = mlb.fit_transform(training_df["symptom_list"])
    y = training_df["disease"]

    model = RandomForestClassifier(
        n_estimators=120,
        max_depth=25,
        min_samples_leaf=1,
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X, y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Save model bundle used by backend to avoid repeated CSV searching.
    model_bundle = {
        "model": model,
        "mlb": mlb,
        "feature_names": mlb.classes_.tolist(),
        "disease_name_map": dict(zip(training_df["disease"], training_df["dataset_name"])),
    }
    with open(MODEL_DIR / "model.pkl", "wb") as file_obj:
        pickle.dump(model_bundle, file_obj)

    # Save symptom vocabulary separately for stable API loading.
    with open(MODEL_DIR / "symptom_list.pkl", "wb") as file_obj:
        pickle.dump(mlb.classes_.tolist(), file_obj)

    print(f"Trained on {len(training_df)} diseases and {len(mlb.classes_)} unique symptoms.")
    print(f"Saved model bundle: {MODEL_DIR / 'model.pkl'}")
    print(f"Saved symptom list: {MODEL_DIR / 'symptom_list.pkl'}")


if __name__ == "__main__":
    train_and_save()
