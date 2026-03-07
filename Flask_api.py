#Flask_API.py

import os
import argparse
import json
import csv
import random
import numpy as np
import pandas as pd
import joblib
from tensorflow.keras import layers, models
import tensorflow as tf
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid
from datetime import datetime, timezone
from flask_cors import CORS
from sklearn.preprocessing import OneHotEncoder, MinMaxScaler
from sklearn.compose import ColumnTransformer

# ----------------------- CONFIG -----------------------
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
LEGIT_CSV_PATH = os.path.join(PROJECT_ROOT, "legit_transactions.csv")
PREPROCESSOR_PATH = os.path.join(PROJECT_ROOT, "preprocessor.pkl")
AUTOENCODER_PATH = os.path.join(PROJECT_ROOT, "fraud_autoencoder_model.keras")
USER_THRESHOLDS_PATH = os.path.join(PROJECT_ROOT, "user_thresholds.json")
CATEGORY_THRESHOLDS_PATH = os.path.join(PROJECT_ROOT, "category_thresholds.json")
LOG_PATH = os.path.join(PROJECT_ROOT, "transaction_logs.json")

ADAPTIVE_PERCENTILE = 95
TOP_FEATURES_COUNT = 10

MIN_USER_TXNS_FOR_PERSONAL_THRESHOLD = 100
RETRAIN_EVERY_N_LEGIT_TXNS = 5
RETRAIN_STATE_PATH = os.path.join(PROJECT_ROOT, "retrain_state.json")

RETRAIN_SEED = 42
RETRAIN_REFIT_PREPROCESSOR = False
RETRAIN_FINE_TUNE_EPOCHS = 5
RETRAIN_FULL_EPOCHS = 25
RETRAIN_BATCH_SIZE = 256

# ----------------------- THREADING -----------------------
PREDICTION_POOL = ThreadPoolExecutor(max_workers=4)
THRESHOLD_LOCK = threading.Lock()
CSV_LOCK = threading.Lock()

RETRAIN_LOCK = threading.Lock()
RETRAIN_POOL = ThreadPoolExecutor(max_workers=1)
RETRAIN_FUTURE = None

USER_LEGIT_STATS_LOCK = threading.Lock()
USER_LEGIT_STATS = {}

# ----------------------- UTILS -----------------------

def load_preprocessor(path=PREPROCESSOR_PATH):
    """Load the fitted sklearn preprocessing pipeline from disk."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Preprocessor not found at {path}")
    return joblib.load(path)

def load_autoencoder(path=AUTOENCODER_PATH):
    """Load the trained Keras autoencoder model from disk."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Autoencoder not found at {path}")
    return models.load_model(path)

def load_user_thresholds(path=USER_THRESHOLDS_PATH):
    """Load per-user anomaly thresholds from JSON (user_id -> threshold)."""
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_user_thresholds(thresholds, path=USER_THRESHOLDS_PATH):
    """Persist per-user thresholds to JSON."""
    with open(path, "w") as f:
        json.dump(thresholds, f, indent=4)

def load_category_thresholds(path=CATEGORY_THRESHOLDS_PATH):
    """Load per-category anomaly thresholds from JSON (category -> threshold)."""
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_category_thresholds(thresholds, path=CATEGORY_THRESHOLDS_PATH):
    """Persist per-category thresholds to JSON."""
    with open(path, "w") as f:
        json.dump(thresholds, f, indent=4)

def load_user_category_map(path=LEGIT_CSV_PATH):
    """Build a mapping of user_id -> user_category from the legit CSV (if available)."""
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path, usecols=["User_ID", "User_Category"]).drop_duplicates()
        return df.set_index("User_ID")["User_Category"].to_dict()
    except Exception:
        return {}

def _load_user_legit_stats(path=LEGIT_CSV_PATH):
    """Load cached per-user running stats (avg_amount, avg_frequency, count) from legit CSV."""
    stats = {}
    if not os.path.exists(path):
        return stats
    try:
        with open(path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row.get("User_ID")
                if not uid:
                    continue
                try:
                    avg_amt = float(row.get("Avg_Transaction_Amount") or 0)
                except Exception:
                    avg_amt = 0
                try:
                    avg_freq = float(row.get("Avg_Transaction_Frequency") or 1.0)
                except Exception:
                    avg_freq = 1.0
                prev = stats.get(uid)
                if prev is None:
                    stats[uid] = {"avg_amount": avg_amt, "avg_frequency": avg_freq, "count": 1}
                else:
                    prev["avg_amount"] = avg_amt
                    prev["avg_frequency"] = avg_freq
                    prev["count"] += 1
    except Exception:
        return stats
    return stats

def _get_user_legit_stats(user_id: str):
    """Return cached per-user stats: (avg_amount, avg_frequency, count).

    Falls back to (0.0, 1.0, 0) when user is unknown.
    """
    if not user_id:
        return 0.0, 1.0, 0
    with USER_LEGIT_STATS_LOCK:
        if not USER_LEGIT_STATS:
            USER_LEGIT_STATS.update(_load_user_legit_stats())
        s = USER_LEGIT_STATS.get(user_id)
        if not s:
            return 0.0, 1.0, 0
        return float(s.get("avg_amount", 0.0)), float(s.get("avg_frequency", 1.0)), int(s.get("count", 0))

def preprocess_single(txn, preprocessor):
    """Convert a single transaction dict into a preprocessed model input array."""
    df = pd.DataFrame([txn])
    if 'Timestamp' in df.columns:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df['Hour'] = df['Timestamp'].dt.hour
        df['DayOfWeek'] = df['Timestamp'].dt.weekday
        df['DayOfMonth'] = df['Timestamp'].dt.day
        df.drop('Timestamp', axis=1, inplace=True)
    X = preprocessor.transform(df).astype('float32')
    return X, df

def compute_top_features(X, recon, feature_names, top_n=TOP_FEATURES_COUNT):
    """Return top-N features with highest reconstruction error contribution for a single sample."""
    errors = np.square(X - recon)[0]
    top_idx = np.argsort(errors)[::-1][:top_n]
    return [[feature_names[i], float(errors[i])] for i in top_idx]

def load_logs():
    """Load transaction logs (dashboard visibility) from JSON."""
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r") as f:
        return json.load(f)

def save_log(entry):
    """Append a log entry to transaction_logs.json."""
    logs = load_logs()
    logs.append(entry)
    with open(LOG_PATH, "w") as f:
        json.dump(logs, f, indent=4)

def _load_retrain_state(path=RETRAIN_STATE_PATH):
    """Load retraining state (legit_since_retrain, last_retrain_at) from JSON."""
    if not os.path.exists(path):
        return {"legit_since_retrain": 0, "last_retrain_at": None, "last_legit_row_count": 0}
    try:
        with open(path, "r") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            return {"legit_since_retrain": 0, "last_retrain_at": None, "last_legit_row_count": 0}
        if "legit_since_retrain" not in state:
            state["legit_since_retrain"] = 0
        if "last_retrain_at" not in state:
            state["last_retrain_at"] = None
        if "last_legit_row_count" not in state:
            state["last_legit_row_count"] = 0
        return state
    except Exception:
        return {"legit_since_retrain": 0, "last_retrain_at": None, "last_legit_row_count": 0}

def _save_retrain_state(state, path=RETRAIN_STATE_PATH):
    """Persist retraining state to JSON (best-effort)."""
    try:
        with open(path, "w") as f:
            json.dump(state, f, indent=4)
    except Exception:
        return

def _prepare_df_for_model(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare a dataframe for model training/inference by normalizing Timestamp into numeric parts."""
    df = df.copy()
    if "Fraud" in df.columns:
        df.drop("Fraud", axis=1, inplace=True)
    if "Timestamp" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df["Hour"] = df["Timestamp"].dt.hour.fillna(0).astype(int)
        df["DayOfWeek"] = df["Timestamp"].dt.weekday.fillna(0).astype(int)
        df["DayOfMonth"] = df["Timestamp"].dt.day.fillna(1).astype(int)
        df.drop("Timestamp", axis=1, inplace=True)
    return df

def _compute_user_threshold_from_legit_csv(user_id: str):
    """Compute a per-user threshold (percentile of reconstruction errors) from legit history."""
    if not user_id or not os.path.exists(LEGIT_CSV_PATH):
        return None
    try:
        df = pd.read_csv(LEGIT_CSV_PATH)
    except Exception:
        return None
    if "Fraud" in df.columns:
        df = df[df["Fraud"] == 0]
    if "User_ID" not in df.columns:
        return None
    df_user = df[df["User_ID"] == user_id].copy()
    if len(df_user) < MIN_USER_TXNS_FOR_PERSONAL_THRESHOLD:
        return None

    df_user = _prepare_df_for_model(df_user)
    if len(df_user) == 0:
        return None
    try:
        with THRESHOLD_LOCK:
            preprocessor = PREPROCESSOR
            autoencoder = AUTOENCODER
        X_user = preprocessor.transform(df_user).astype("float32")
        recon_user = autoencoder.predict(X_user, verbose=0)
        errors = np.mean(np.square(X_user - recon_user), axis=1)
        return float(np.percentile(errors, ADAPTIVE_PERCENTILE))
    except Exception:
        return None

def _maybe_create_user_threshold(user_id: str):
    """Create and persist a per-user threshold once the user has enough legit history."""
    if not user_id:
        return
    if user_id in USER_THRESHOLDS:
        return
    _, _, count = _get_user_legit_stats(user_id)
    if int(count) < MIN_USER_TXNS_FOR_PERSONAL_THRESHOLD:
        return
    thr = _compute_user_threshold_from_legit_csv(user_id)
    if thr is None:
        return
    with THRESHOLD_LOCK:
        if user_id in USER_THRESHOLDS:
            return
        USER_THRESHOLDS[user_id] = float(thr)
        save_user_thresholds(USER_THRESHOLDS)

def _recompute_feature_names(preprocessor):
    """Recompute flattened feature names from the ColumnTransformer (OHE + numeric)."""
    cat_cols = preprocessor.transformers_[0][2]
    num_cols = preprocessor.transformers_[1][2]
    ohe = preprocessor.transformers_[0][1]
    cat_names = ohe.get_feature_names_out(cat_cols)
    return list(cat_names) + list(num_cols)

def _retrain_global_model():
    """Retrain the global autoencoder and refresh thresholds from legit_transactions.csv.

    Runs in a background thread; updates global PREPROCESSOR/AUTOENCODER and threshold JSONs.
    """
    global PREPROCESSOR, AUTOENCODER, USER_THRESHOLDS, CATEGORY_THRESHOLDS, USER_CATEGORY_MAP, FEATURE_NAMES, USER_LEGIT_STATS

    if not os.path.exists(LEGIT_CSV_PATH):
        return False
    try:
        df = pd.read_csv(LEGIT_CSV_PATH)
    except Exception:
        return False
    if "Fraud" in df.columns:
        df = df[df["Fraud"] == 0].copy()
    if len(df) == 0:
        return False

    os.environ["PYTHONHASHSEED"] = str(RETRAIN_SEED)
    random.seed(RETRAIN_SEED)
    np.random.seed(RETRAIN_SEED)
    try:
        tf.random.set_seed(RETRAIN_SEED)
    except Exception:
        pass

    df_legit = _prepare_df_for_model(df)

    state = _load_retrain_state()
    try:
        last_count = int(state.get("last_legit_row_count") or 0)
    except Exception:
        last_count = 0

    if last_count == 0 and state.get("last_retrain_at") is not None:
        last_count = int(len(df_legit))
        state["last_legit_row_count"] = last_count
        _save_retrain_state(state)

    try:
        new_rows_df = df_legit.iloc[last_count:].copy()
    except Exception:
        new_rows_df = df_legit.copy()

    if len(new_rows_df) == 0:
        state["legit_since_retrain"] = 0
        state["last_retrain_at"] = datetime.now(timezone.utc).isoformat()
        state["last_legit_row_count"] = int(len(df_legit))
        _save_retrain_state(state)
        return True

    with THRESHOLD_LOCK:
        preprocessor_current = PREPROCESSOR
        autoencoder_current = AUTOENCODER
        user_thresholds_current = dict(USER_THRESHOLDS)
        category_thresholds_current = dict(CATEGORY_THRESHOLDS)
        user_category_map_current = dict(USER_CATEGORY_MAP)

    preprocessor = preprocessor_current
    if RETRAIN_REFIT_PREPROCESSOR:
        cat_cols = [
            "User_ID","User_Category","Transaction_Channel","Payment_Method",
            "Merchant_Category","Currency","Device_Type","Device_Location",
            "Transaction_IP_Address_Location","IP_Risk_Score"
        ]
        num_cols = [col for col in df_legit.columns if col not in cat_cols]
        preprocessor = ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
            ("num", MinMaxScaler(), num_cols)
        ])
        _ = preprocessor.fit_transform(df_legit)
        joblib.dump(preprocessor, PREPROCESSOR_PATH)

    X_new = preprocessor.transform(new_rows_df).astype("float32")
    input_dim = int(X_new.shape[1])

    autoencoder = autoencoder_current
    can_fine_tune = False
    try:
        model_in_dim = int(autoencoder.input_shape[-1])
        can_fine_tune = model_in_dim == input_dim
    except Exception:
        can_fine_tune = False

    if not can_fine_tune:
        autoencoder = models.Sequential([
            layers.Input(shape=(input_dim,)),
            layers.Dense(64, activation="relu"),
            layers.Dense(32, activation="relu"),
            layers.Dense(16, activation="relu"),
            layers.Dense(32, activation="relu"),
            layers.Dense(64, activation="relu"),
            layers.Dense(input_dim, activation="linear"),
        ])
        autoencoder.compile(optimizer="adam", loss="mse")
        X_full = preprocessor.transform(df_legit).astype("float32")
        autoencoder.fit(
            X_full, X_full,
            epochs=RETRAIN_FULL_EPOCHS,
            batch_size=RETRAIN_BATCH_SIZE,
            validation_split=0.1,
            shuffle=True,
            verbose=0,
        )
    else:
        if last_count == 0:
            try:
                autoencoder.compile(optimizer="adam", loss="mse")
            except Exception:
                pass
            X_full = preprocessor.transform(df_legit).astype("float32")
            autoencoder.fit(
                X_full, X_full,
                epochs=RETRAIN_FULL_EPOCHS,
                batch_size=RETRAIN_BATCH_SIZE,
                validation_split=0.1,
                shuffle=True,
                verbose=0,
            )
        else:
            try:
                autoencoder.compile(optimizer="adam", loss="mse")
            except Exception:
                pass
            autoencoder.fit(
                X_new, X_new,
                epochs=RETRAIN_FINE_TUNE_EPOCHS,
                batch_size=RETRAIN_BATCH_SIZE,
                validation_split=0.0,
                shuffle=True,
                verbose=0,
            )

    autoencoder.save(AUTOENCODER_PATH)

    user_category_map = user_category_map_current
    if "User_ID" in df.columns and "User_Category" in df.columns:
        user_category_map = (
            df[["User_ID", "User_Category"]]
            .drop_duplicates()
            .set_index("User_ID")["User_Category"]
            .to_dict()
        )

    impacted_users = set()
    impacted_categories = set()
    if "User_ID" in new_rows_df.columns:
        for uid in new_rows_df["User_ID"].dropna().unique():
            impacted_users.add(str(uid))
            cat = user_category_map.get(uid)
            if cat is not None:
                impacted_categories.add(str(cat))
    if "User_Category" in new_rows_df.columns:
        for cat in new_rows_df["User_Category"].dropna().unique():
            impacted_categories.add(str(cat))

    user_thresholds = user_thresholds_current
    category_thresholds = category_thresholds_current

    X_imp = preprocessor.transform(df_legit).astype("float32")
    recon_imp = autoencoder.predict(X_imp, verbose=0)
    errors_all = np.mean(np.square(X_imp - recon_imp), axis=1)

    if "User_ID" in df_legit.columns and impacted_users:
        for uid in impacted_users:
            try:
                mask = (df_legit["User_ID"].astype(str) == uid).to_numpy()
            except Exception:
                continue
            user_errors = errors_all[mask]
            if user_errors.size == 0:
                continue
            if int(user_errors.size) < MIN_USER_TXNS_FOR_PERSONAL_THRESHOLD:
                if uid in user_thresholds:
                    user_thresholds.pop(uid, None)
                continue
            user_thresholds[uid] = float(np.percentile(user_errors, ADAPTIVE_PERCENTILE))

    if "User_Category" in df_legit.columns and impacted_categories:
        for category in impacted_categories:
            try:
                mask = (df_legit["User_Category"].astype(str) == category).to_numpy()
            except Exception:
                continue
            cat_errors = errors_all[mask]
            if cat_errors.size == 0:
                continue
            category_thresholds[str(category)] = float(np.percentile(cat_errors, ADAPTIVE_PERCENTILE))

    with THRESHOLD_LOCK:
        if RETRAIN_REFIT_PREPROCESSOR:
            PREPROCESSOR = load_preprocessor()
        AUTOENCODER = load_autoencoder()
        USER_THRESHOLDS = user_thresholds
        CATEGORY_THRESHOLDS = category_thresholds
        USER_CATEGORY_MAP = user_category_map
        FEATURE_NAMES = _recompute_feature_names(PREPROCESSOR)
        USER_LEGIT_STATS = {}
        save_user_thresholds(USER_THRESHOLDS)
        save_category_thresholds(CATEGORY_THRESHOLDS)

    state = _load_retrain_state()
    state["legit_since_retrain"] = 0
    state["last_retrain_at"] = datetime.now(timezone.utc).isoformat()
    state["last_legit_row_count"] = int(len(df_legit))
    _save_retrain_state(state)
    return True

def _schedule_retrain_if_needed():
    """Increment retrain counter and schedule background retraining when threshold is reached."""
    global RETRAIN_FUTURE
    state = _load_retrain_state()
    try:
        state["legit_since_retrain"] = int(state.get("legit_since_retrain") or 0) + 1
    except Exception:
        state["legit_since_retrain"] = 1
    _save_retrain_state(state)

    try:
        if int(state.get("legit_since_retrain") or 0) < RETRAIN_EVERY_N_LEGIT_TXNS:
            return False
    except Exception:
        return False

    with RETRAIN_LOCK:
        if RETRAIN_FUTURE is not None and not RETRAIN_FUTURE.done():
            return False
        RETRAIN_FUTURE = RETRAIN_POOL.submit(_retrain_global_model)
        return True

def _get_last_n_user_values_from_logs(user_id: str, key: str, n: int = 10):
    """Return last N values for a given key from transaction_logs.json for a specific user."""
    if not user_id:
        return []
    try:
        logs = load_logs()
    except Exception:
        return []
    out = []
    for l in reversed(logs):
        if l.get("user_id") != user_id:
            continue
        v = l.get(key)
        if v is None:
            continue
        out.append(v)
        if len(out) >= n:
            break
    return out

def _apply_history_features(txn):
    """Compute behavioral change flags (payment/merchant/device) using the user's recent logs."""
    user_id = txn.get("User_ID")
    payment_method = txn.get("Payment_Method")
    merchant_category = txn.get("Merchant_Category")
    device_type = txn.get("Device_Type")
    if not user_id:
        return

    prev_methods = _get_last_n_user_values_from_logs(user_id, "payment_method", 10)
    prev_merchants = _get_last_n_user_values_from_logs(user_id, "merchant_category", 10)
    prev_devices = _get_last_n_user_values_from_logs(user_id, "device_type", 10)

    if payment_method:
        txn["Payment_Method_Change"] = 0 if (len(prev_methods) == 0 or payment_method in prev_methods) else 1

    if merchant_category:
        txn["Merchant_Change"] = 0 if (len(prev_merchants) == 0 or merchant_category in prev_merchants) else 1

    if device_type:
        txn["Device_Change"] = 0 if (len(prev_devices) == 0 or device_type in prev_devices) else 1

def append_transaction_to_legit_csv(txn, fraud_label: int):
    """Append a transaction row to legit_transactions.csv (thread-safe)."""
    fieldnames = [
        "User_ID","User_Category","Transaction_Amount","Transaction_Channel",
        "Payment_Method","Timestamp","Merchant_Category","Currency",
        "Device_Type","Device_Location","Transaction_IP_Address_Location",
        "Transaction_Frequency","Avg_Transaction_Amount",
        "Avg_Transaction_Frequency","Deviation_Amount","Location_Deviation",
        "Device_Change","IP_Risk_Score",
        "Merchant_Change","Payment_Method_Change","Is_Weekend","Is_Night","Fraud"
    ]

    row = {
        "User_ID": txn.get("User_ID"),
        "User_Category": txn.get("User_Category"),
        "Transaction_Amount": txn.get("Transaction_Amount"),
        "Transaction_Channel": txn.get("Transaction_Channel"),
        "Payment_Method": txn.get("Payment_Method"),
        "Timestamp": txn.get("Timestamp"),
        "Merchant_Category": txn.get("Merchant_Category"),
        "Currency": txn.get("Currency"),
        "Device_Type": txn.get("Device_Type"),
        "Device_Location": txn.get("Device_Location"),
        "Transaction_IP_Address_Location": txn.get("Transaction_IP_Address_Location"),
        "Transaction_Frequency": txn.get("Transaction_Frequency", 0),
        "Avg_Transaction_Amount": txn.get("Avg_Transaction_Amount", 0),
        "Avg_Transaction_Frequency": txn.get("Avg_Transaction_Frequency", 0),
        "Deviation_Amount": txn.get("Deviation_Amount", 0),
        "Location_Deviation": txn.get("Location_Deviation", 0),
        "Device_Change": txn.get("Device_Change", 0),
        "IP_Risk_Score": txn.get("IP_Risk_Score"),
        "Merchant_Change": txn.get("Merchant_Change", 0),
        "Payment_Method_Change": txn.get("Payment_Method_Change", 0),
        "Is_Weekend": txn.get("Is_Weekend", 0),
        "Is_Night": txn.get("Is_Night", 0),
        "Fraud": int(fraud_label),
    }

    file_exists = os.path.exists(LEGIT_CSV_PATH)
    with CSV_LOCK:
        if file_exists:
            try:
                with open(LEGIT_CSV_PATH, "r", newline="") as rf:
                    reader = csv.reader(rf)
                    existing_header = next(reader, None)
                if existing_header != fieldnames:
                    raise ValueError(
                        "legit_transactions.csv header does not match expected schema. "
                        "Regenerate the dataset/training artifacts (dataset.py + train.py) or delete the old legit_transactions.csv."
                    )
            except Exception:
                raise

        with open(LEGIT_CSV_PATH, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({k: row.get(k) for k in fieldnames})

# -------------------- LOAD MODELS & THRESHOLDS --------------------
PREPROCESSOR = load_preprocessor()
AUTOENCODER = load_autoencoder()
USER_THRESHOLDS = load_user_thresholds()
CATEGORY_THRESHOLDS = load_category_thresholds()
USER_CATEGORY_MAP = load_user_category_map()

cat_cols = PREPROCESSOR.transformers_[0][2]
num_cols = PREPROCESSOR.transformers_[1][2]
ohe = PREPROCESSOR.transformers_[0][1]
cat_names = ohe.get_feature_names_out(cat_cols)
FEATURE_NAMES = list(cat_names) + list(num_cols)

# -------------------- FLASK APP --------------------
app = Flask(__name__)
CORS(app)

def _compute_category_threshold(category: str):
    """Compute a category threshold as median of existing per-user thresholds in that category."""
    values = [
        float(thr)
        for uid, thr in USER_THRESHOLDS.items()
        if USER_CATEGORY_MAP.get(uid) == category
    ]
    if not values:
        return None
    return float(np.median(values))

def get_threshold_for_txn(txn):
    """Select the threshold for a transaction using user thresholds (if eligible) else category/default."""
    user_id = txn.get("User_ID")
    if user_id and user_id in USER_THRESHOLDS:
        try:
            _, _, count = _get_user_legit_stats(user_id)
            if int(count) >= MIN_USER_TXNS_FOR_PERSONAL_THRESHOLD:
                return float(USER_THRESHOLDS[user_id]), "user"
        except Exception:
            pass

    if user_id:
        _maybe_create_user_threshold(user_id)
        if user_id in USER_THRESHOLDS:
            try:
                _, _, count = _get_user_legit_stats(user_id)
                if int(count) >= MIN_USER_TXNS_FOR_PERSONAL_THRESHOLD:
                    return float(USER_THRESHOLDS[user_id]), "user"
            except Exception:
                pass

    category = txn.get("User_Category")
    if not category and user_id:
        category = USER_CATEGORY_MAP.get(user_id)

    if user_id and category:
        USER_CATEGORY_MAP[user_id] = category

    if category:
        if category in CATEGORY_THRESHOLDS:
            return float(CATEGORY_THRESHOLDS[category]), "category"
        computed = _compute_category_threshold(category)
        if computed is not None:
            CATEGORY_THRESHOLDS[category] = computed
            save_category_thresholds(CATEGORY_THRESHOLDS)
            return float(computed), "category"

    return 0.02, "default"

def _compute_user_stats_from_logs(user_id: str):
    """Compatibility wrapper for fetching per-user legit stats."""
    return _get_user_legit_stats(user_id)

def _compute_location_deviation(current_location: str, user_id: str):
    """Compute location deviation based on user's previous locations"""
    prev_locations = _get_last_n_user_values_from_logs(user_id, "device_location", 10)
    if not prev_locations:
        return 0
    return 0 if current_location in prev_locations else 1

def _compute_automatic_features(txn):
    """Compute features automatically from minimal input"""
    user_id = txn.get("User_ID")
    current_amount = txn.get("Transaction_Amount", 0)
    device_location = txn.get("Device_Location", "")
    txn_location = txn.get("Transaction_IP_Address_Location", "")
    current_frequency = txn.get("Transaction_Frequency", 1)
    
    # Get user statistics from logs
    avg_amount, avg_frequency, prev_count = _get_user_legit_stats(user_id)
    
    # Compute deviation amount
    deviation_amount = abs(current_amount - avg_amount) if avg_amount > 0 else 0

    # Compute location deviation
    dl = str(device_location or "").strip().lower()
    tl = str(txn_location or "").strip().lower()
    if dl and tl:
        location_deviation = 0 if dl == tl else 1
    else:
        location_deviation = _compute_location_deviation(device_location, user_id)
    
    # Set computed features
    txn["Avg_Transaction_Amount"] = avg_amount
    txn["Avg_Transaction_Frequency"] = avg_frequency
    txn["Deviation_Amount"] = deviation_amount
    txn["Location_Deviation"] = location_deviation
    
    # Set default values for features that will be computed by history
    if "Payment_Method_Change" not in txn:
        txn["Payment_Method_Change"] = 0
    if "Merchant_Change" not in txn:
        txn["Merchant_Change"] = 0
    if "Device_Change" not in txn:
        txn["Device_Change"] = 0

    denom = prev_count + 1
    next_avg_amount = (avg_amount * prev_count + float(current_amount)) / denom if denom > 0 else float(current_amount)
    next_avg_frequency = (avg_frequency * prev_count + float(current_frequency)) / denom if denom > 0 else float(current_frequency)
    return {
        "legit_count_next": denom,
        "avg_amount_used": avg_amount,
        "avg_frequency_used": avg_frequency,
        "avg_amount_next": next_avg_amount,
        "avg_frequency_next": next_avg_frequency,
    }

def threaded_predict(txn, threshold, preprocessor, autoencoder):
    """Run model inference for a single transaction and return (X, recon, error, is_anomaly)."""
    X, _ = preprocess_single(txn, preprocessor)
    recon = autoencoder.predict(X, verbose=0)
    error = float(np.mean(np.square(X - recon)))
    is_anomaly = error > threshold
    return X, recon, error, is_anomaly

@app.route('/predict', methods=['POST'])
def predict():
    """API endpoint: score a transaction, optionally confirm legit to adapt thresholds."""
    global PREPROCESSOR, AUTOENCODER, USER_THRESHOLDS, CATEGORY_THRESHOLDS, USER_CATEGORY_MAP

    data = request.get_json()
    if not data or 'transaction' not in data:
        return jsonify({"error": "Invalid JSON, provide 'transaction' key"}), 400

    txn = data['transaction']
    confirm = data.get('confirm', False)

    # Compute automatic features from minimal input
    computed_meta = _compute_automatic_features(txn)
    
    # Apply history features (payment method, merchant, device changes)
    _apply_history_features(txn)
    
    # Print computed features to terminal
    print("\n=== Computed Features ===")
    print(f"User_ID: {txn.get('User_ID')}")
    print(f"Avg_Transaction_Amount: {txn.get('Avg_Transaction_Amount', 0):.2f}")
    print(f"Avg_Transaction_Frequency: {txn.get('Avg_Transaction_Frequency', 0):.2f}")
    if computed_meta:
        print(f"Avg_Transaction_Amount_Next: {float(computed_meta.get('avg_amount_next', 0)):.2f}")
        print(f"Avg_Transaction_Frequency_Next: {float(computed_meta.get('avg_frequency_next', 0)):.2f}")
    print(f"Deviation_Amount: {txn.get('Deviation_Amount', 0):.2f}")
    print(f"Location_Deviation: {txn.get('Location_Deviation', 0)}")
    print(f"Payment_Method_Change: {txn.get('Payment_Method_Change', 0)}")
    print(f"Merchant_Change: {txn.get('Merchant_Change', 0)}")
    print(f"Device_Change: {txn.get('Device_Change', 0)}")
    print("========================\n")

    user_id = txn.get("User_ID")
    threshold, threshold_source = get_threshold_for_txn(txn)

    prev_legit_count = 0
    try:
        if computed_meta and computed_meta.get("legit_count_next") is not None:
            prev_legit_count = max(0, int(computed_meta.get("legit_count_next")) - 1)
    except Exception:
        prev_legit_count = 0

    is_new_user = bool(user_id) and (user_id not in USER_THRESHOLDS) and (prev_legit_count == 0)

    try:
        preprocessor = PREPROCESSOR
        autoencoder = AUTOENCODER
        future = PREDICTION_POOL.submit(threaded_predict, txn, threshold, preprocessor, autoencoder)
        X, recon, error, is_anomaly = future.result()
    except Exception as e:
        return jsonify({"error": f"Prediction error: {e}"}), 500

    result = {
        "is_anomaly": bool(is_anomaly),
        "reconstruction_error": error,
        "threshold_used": threshold,
        "threshold_source": threshold_source
    }

    if (not confirm) and is_new_user and int(txn.get("Location_Deviation") or 0) == 1:
        is_anomaly = True
        result["is_anomaly"] = True
        result["fraud_rule_applied"] = True
        result["fraud_rule"] = "new_user_location_mismatch"

    if user_id and confirm and is_anomaly:
        with THRESHOLD_LOCK:
            current_threshold = USER_THRESHOLDS.get(user_id, threshold)
            new_threshold = max(current_threshold, error)
            USER_THRESHOLDS[user_id] = new_threshold
            save_user_thresholds(USER_THRESHOLDS)

            category = txn.get("User_Category") or USER_CATEGORY_MAP.get(user_id)
            if category:
                USER_CATEGORY_MAP[user_id] = category
                computed = _compute_category_threshold(category)
                if computed is not None:
                    CATEGORY_THRESHOLDS[category] = computed
                    save_category_thresholds(CATEGORY_THRESHOLDS)
        result['threshold_updated'] = True
        result['new_threshold'] = new_threshold

    if is_anomaly and not confirm:
        try:
            top_features = compute_top_features(X, recon, FEATURE_NAMES)
            result['top_features'] = top_features
        except Exception as e:
            result['xai_error'] = str(e)

    # Persist minimal transaction fields for dashboard visibility
    log_entry = {
        "transaction_id": str(uuid.uuid4()),
        "user_id": user_id,
        "amount": txn.get("Transaction_Amount"),
        "timestamp": txn.get("Timestamp") or datetime.now(timezone.utc).isoformat(),
        "transaction_channel": txn.get("Transaction_Channel"),
        "payment_method": txn.get("Payment_Method"),
        "merchant_category": txn.get("Merchant_Category"),
        "device_type": txn.get("Device_Type"),
        "device_location": txn.get("Device_Location"),
        "transaction_ip_address_location": txn.get("Transaction_IP_Address_Location"),
        "transaction_frequency": txn.get("Transaction_Frequency"),
        "avg_transaction_amount_used": computed_meta.get("avg_amount_used") if computed_meta else None,
        "avg_transaction_frequency_used": computed_meta.get("avg_frequency_used") if computed_meta else None,
        "avg_transaction_amount_next": computed_meta.get("avg_amount_next") if computed_meta else None,
        "avg_transaction_frequency_next": computed_meta.get("avg_frequency_next") if computed_meta else None,
        "legit_count_next": computed_meta.get("legit_count_next") if computed_meta else None,
        "reconstruction_error": error,
        "threshold": threshold,
        "is_anomaly": bool(is_anomaly),
        "confirmed_legit": bool(confirm),
        "top_features": result.get("top_features", [])
    }

    save_log(log_entry)

    # Only append to legit_transactions.csv if the transaction is confirmed as legitimate
    if not is_anomaly or confirm:
        fraud_label = 0  # Always 0 since we're only saving legit transactions
        try:
            if computed_meta:
                txn["Avg_Transaction_Amount"] = float(computed_meta.get("avg_amount_next", txn.get("Avg_Transaction_Amount", 0)))
                txn["Avg_Transaction_Frequency"] = float(computed_meta.get("avg_frequency_next", txn.get("Avg_Transaction_Frequency", 0)))
            append_transaction_to_legit_csv(txn, fraud_label)
            if user_id and computed_meta:
                with USER_LEGIT_STATS_LOCK:
                    USER_LEGIT_STATS[user_id] = {
                        "avg_amount": float(computed_meta.get("avg_amount_next", 0.0)),
                        "avg_frequency": float(computed_meta.get("avg_frequency_next", 1.0)),
                        "count": int(computed_meta.get("legit_count_next", 0)),
                    }
            if user_id:
                _maybe_create_user_threshold(user_id)
            if _schedule_retrain_if_needed():
                result["retrain_scheduled"] = True
        except Exception as e:
            result["csv_append_error"] = str(e)

    return jsonify(result)

@app.route("/stats", methods=["GET"])
def stats():
    """API endpoint: return dashboard aggregate counts (total/fraud/legit)."""
    logs = load_logs()
    total = len(logs)
    fraud = sum(1 for l in logs if l["is_anomaly"])
    legit = total - fraud
    return jsonify({
        "total": total,
        "fraud": fraud,
        "legit": legit
    })

@app.route("/logs", methods=["GET"])
def logs():
    """API endpoint: return raw transaction logs for the dashboard."""
    return jsonify(load_logs())

# -------------------- CLI --------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()

    print(f"Starting Flask server on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)

