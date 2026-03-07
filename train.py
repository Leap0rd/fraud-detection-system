import pandas as pd
import numpy as np
import joblib
import json
from tensorflow.keras import layers, models
from sklearn.preprocessing import OneHotEncoder, MinMaxScaler
from sklearn.compose import ColumnTransformer
from sklearn.metrics import classification_report, roc_auc_score
import os

# -----------------------------
# 1. Load dataset
# -----------------------------
df = pd.read_csv("legit_transactions.csv")

# Only legitimate transactions
df_legit = df[df["Fraud"] == 0].copy()
df_legit.drop("Fraud", axis=1, inplace=True)

# -----------------------------
# 2. Timestamp to numeric
# -----------------------------
df_legit['Timestamp'] = pd.to_datetime(df_legit['Timestamp'])
df_legit['Hour'] = df_legit['Timestamp'].dt.hour
df_legit['DayOfWeek'] = df_legit['Timestamp'].dt.weekday
df_legit['DayOfMonth'] = df_legit['Timestamp'].dt.day
df_legit.drop('Timestamp', axis=1, inplace=True)

# -----------------------------
# 3. Columns
# -----------------------------
cat_cols = [
    "User_ID","User_Category","Transaction_Channel","Payment_Method",
    "Merchant_Category","Currency","Device_Type","Device_Location",
    "Transaction_IP_Address_Location","IP_Risk_Score"
]
num_cols = [col for col in df_legit.columns if col not in cat_cols]
print("Numerical columns:", num_cols)

# -----------------------------
# 4. Preprocessor
# -----------------------------
preprocessor = ColumnTransformer([
    ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
    ("num", MinMaxScaler(), num_cols)
])

X_train = preprocessor.fit_transform(df_legit)
X_train = X_train.astype("float32")
joblib.dump(preprocessor, "preprocessor.pkl")

# -----------------------------
# 5. Autoencoder
# -----------------------------
input_dim = X_train.shape[1]
autoencoder = models.Sequential([
    layers.Input(shape=(input_dim,)),
    layers.Dense(64, activation="relu"),
    layers.Dense(32, activation="relu"),
    layers.Dense(16, activation="relu"),
    layers.Dense(32, activation="relu"),
    layers.Dense(64, activation="relu"),
    layers.Dense(input_dim, activation="linear")
])

autoencoder.compile(optimizer="adam", loss="mse")
autoencoder.fit(
    X_train, X_train,
    epochs=25,
    batch_size=256,
    validation_split=0.1,
    shuffle=True
)

autoencoder.save("fraud_autoencoder_model.keras")

# -----------------------------
# 6. Compute per-user threshold
# -----------------------------
user_thresholds = {}

for user_id in df_legit["User_ID"].unique():
    user_df = df_legit[df_legit["User_ID"] == user_id]
    X_user = preprocessor.transform(user_df).astype("float32")
    recon_user = autoencoder.predict(X_user, verbose=0)
    errors = np.mean(np.square(X_user - recon_user), axis=1)
    user_thresholds[user_id] = float(np.percentile(errors, 95))

# -----------------------------
# 7. Compute per-category threshold
# -----------------------------
user_category_map = (
    df_legit[["User_ID", "User_Category"]]
    .drop_duplicates()
    .set_index("User_ID")["User_Category"]
    .to_dict()
)

category_thresholds = {}

for category in df_legit["User_Category"].unique():
    users_in_cat = [uid for uid, cat in user_category_map.items() if cat == category]
    values = [user_thresholds[uid] for uid in users_in_cat if uid in user_thresholds]
    if values:
        category_thresholds[category] = float(np.median(values))

with open("user_thresholds.json", "w") as f:
    json.dump(user_thresholds, f, indent=4)

with open("category_thresholds.json", "w") as f:
    json.dump(category_thresholds, f, indent=4)

print("Per-user thresholds saved successfully!")

# =====================================================
# 8. PERFORMANCE EVALUATION (UNSUPERVISED)
# =====================================================

print("\n--- Unsupervised Evaluation ---")

recon_train = autoencoder.predict(X_train, verbose=0)
train_errors = np.mean(np.square(X_train - recon_train), axis=1)

print("Reconstruction Error Statistics:")
print("Mean Error :", train_errors.mean())
print("Std Error  :", train_errors.std())
print("95th %ile  :", np.percentile(train_errors, 95))
print("99th %ile  :", np.percentile(train_errors, 99))

threshold_global = np.percentile(train_errors, 95)
false_alert_rate = np.mean(train_errors > threshold_global)

print("False Alert Rate on Legit Data:", round(false_alert_rate * 100, 2), "%")

# # =====================================================
# # 9. OPTIONAL SUPERVISED EVALUATION (IF LABELED FILE EXISTS)
# # =====================================================

# if os.path.exists("test_transactions.csv"):
#     print("\n--- Supervised Evaluation (Labeled Test Data) ---")

#     df_test = pd.read_csv("test_transactions.csv")
#     y_true = df_test["Fraud"].values

#     df_test_proc = df_test.drop("Fraud", axis=1)
#     df_test_proc['Timestamp'] = pd.to_datetime(df_test_proc['Timestamp'])
#     df_test_proc['Hour'] = df_test_proc['Timestamp'].dt.hour
#     df_test_proc['DayOfWeek'] = df_test_proc['Timestamp'].dt.weekday
#     df_test_proc['DayOfMonth'] = df_test_proc['Timestamp'].dt.day
#     df_test_proc.drop("Timestamp", axis=1, inplace=True)

#     X_test = preprocessor.transform(df_test_proc).astype("float32")

#     recon_test = autoencoder.predict(X_test, verbose=0)
#     test_errors = np.mean(np.square(X_test - recon_test), axis=1)

#     y_pred = (test_errors > threshold_global).astype(int)

#     print(classification_report(y_true, y_pred))
#     print("ROC-AUC Score:", roc_auc_score(y_true, test_errors))

# else:
#     print("\nNo labeled test file found. Supervised evaluation skipped.")
