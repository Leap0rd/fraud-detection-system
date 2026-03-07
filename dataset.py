#datset.py

import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
from collections import deque

# ---------------- CONFIG ----------------
np.random.seed(42)
random.seed(42)

NUM_USERS = 100
TRANSACTIONS_PER_USER = 10000
CURRENCY = "PKR"

# ---------------- Cities ----------------
pk_cities = [
    "Lahore","Karachi","Islamabad","Rawalpindi","Faisalabad","Peshawar","Quetta","Multan","Sialkot",
    "Hyderabad","Sukkur","Bahawalpur","Gujranwala","Gujrat","Sahiwal","Okara","Jhelum","Mardan",
    "Abbottabad","Swat","Chakwal","Kasur","Sheikhupura","Narowal","Rahim Yar Khan","Dera Ghazi Khan",
    "Dera Ismail Khan","Gwadar","Khuzdar","Zhob","Kohat","Mansehra","Haripur","Attock","Mianwali",
    "Charsadda","Nowshera","Jacobabad","Shikarpur","Larkana","Mirpurkhas","Tando Adam","Tando Allahyar",
    "Badin","Umerkot","Sanghar","Khairpur","Hafizabad","Bhakkar","Toba Tek Singh","Jhang","Layyah",
    "Muzaffargarh","Khanewal","Pakpattan","Vehari","Kharian","Lodhran","Kot Addu","Wah Cantt",
    "Taxila","Murree","Skardu","Gilgit","Hunza","Chitral","Turbat","Panjgur","Hub","Mastung",
    "Tando Jam","Pano Aqil","Jamshoro","Kandiaro","Kotri","Hala","Sujawal"
]

# ---------------- Payment Methods ----------------
payment_methods = [
    "debit_card",
    "credit_card",
    "visa",
    "mastercard",
    "bank_transfer",
    "easypaisa",
    "jazzcash",
    "sadapay"
]

transaction_channels = [
    "mobile_app",
    "internet_banking",
    "ecommerce",
    "pos_swipe",
    "atm_withdrawal",
    "bank_branch",
    "p2p_transfer",
    "utility_bill_payment",
    "mobile_topup"
]

channel_payment_methods = {
    "mobile_app": ["bank_transfer", "easypaisa", "jazzcash", "sadapay"],
    "internet_banking": ["bank_transfer"],
    "ecommerce": ["debit_card", "credit_card", "visa", "mastercard"],
    "pos_swipe": ["debit_card", "credit_card", "visa", "mastercard"],
    "atm_withdrawal": ["debit_card", "visa", "mastercard"],
    "bank_branch": ["bank_transfer"],
    "p2p_transfer": ["bank_transfer", "easypaisa", "jazzcash", "sadapay"],
    "utility_bill_payment": ["bank_transfer", "easypaisa", "jazzcash", "sadapay"],
    "mobile_topup": ["easypaisa", "jazzcash", "sadapay", "bank_transfer"]
}

# ---------------- User Categories ----------------
categories = ["regular", "employee", "traveler", "businessman"]

base_amount = {
    "regular": (200, 3000),
    "employee": (500, 15000),
    "traveler": (1000, 40000),
    "businessman": (5000, 250000)
}

device_types = ["mobile", "laptop", "desktop", "tablet"]
merchant_categories = [
    "groceries","electronics","travel","food",
    "fashion","digital_goods","utilities","mobile_topup"
]

# ---------------- USERS ----------------
user_ids = [f"U{i+1}" for i in range(NUM_USERS)]
user_category_map = {uid: random.choice(categories) for uid in user_ids}

rows = []
start_time = datetime(2025, 1, 1, 8, 0, 0)

# ---------------- GENERATE TRANSACTIONS ----------------
for uid in user_ids:
    category = user_category_map[uid]
    amount_low, amount_high = base_amount[category]
    avg_amount_user = np.mean([amount_low, amount_high])

    for _ in range(TRANSACTIONS_PER_USER):
        # Timestamp
        timestamp = start_time + timedelta(
            days=random.randint(0, 180),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        )
        transaction_date = timestamp.date()
        is_night = 1 if timestamp.hour <= 4 else 0
        is_weekend = 1 if timestamp.weekday() >= 5 else 0

        # Amount
        amount = max(100, np.random.normal(avg_amount_user, avg_amount_user * 0.25))

        # Merchant, Device, Payment
        merchant = random.choice(merchant_categories)
        device = random.choice(device_types)
        transaction_channel = random.choice(transaction_channels)
        payment_method = random.choice(channel_payment_methods[transaction_channel])

        if transaction_channel == "mobile_topup":
            merchant = "mobile_topup"
        elif transaction_channel == "utility_bill_payment":
            merchant = "utilities"

        # Location
        location = random.choice(pk_cities)
        ip_location = random.choice(pk_cities)
        location_dev = 0 if location == ip_location else 1

        # IP Risk
        ip_risk = random.choices(["low","medium","high"], weights=[0.75,0.2,0.05])[0]

        # ---------------- FRAUD RULES ----------------
        deviation_amount = abs(amount - avg_amount_user)
        fraud = 0
        trans_freq = 1
        avg_freq_user = 1
        device_change = 0
        merchant_change = 0
        payment_method_change = 0

        if location_dev == 1:
            fraud = 1
        else:
            fraud_score = 0
            fraud_score += 1 if amount > avg_amount_user*3 else 0
            fraud_score += 1 if deviation_amount > avg_amount_user*1.5 else 0
            fraud_score += 1 if ip_risk=="high" else 0
            fraud_score += 1 if device_change==1 else 0
            fraud_score += 1 if payment_method_change==1 else 0
            fraud_score += 1 if merchant_change==1 else 0
            fraud_score += 1 if trans_freq > avg_freq_user*3 else 0
            fraud_score += 1 if (is_weekend==1 and is_night==1) else 0
            fraud = 1 if fraud_score>4 else 0

        rows.append([
            uid, category, round(amount,2),
            transaction_channel,
            payment_method, timestamp, merchant, CURRENCY,
            device, location, ip_location,
            0,0,0,0,location_dev,device_change,ip_risk,merchant_change,payment_method_change,is_weekend,is_night,fraud
        ])

# ---------------- CREATE DATAFRAME ----------------
columns = [
    "User_ID","User_Category","Transaction_Amount","Transaction_Channel",
    "Payment_Method","Timestamp","Merchant_Category","Currency",
    "Device_Type","Device_Location","Transaction_IP_Address_Location",
    "Transaction_Frequency","Avg_Transaction_Amount",
    "Avg_Transaction_Frequency","Deviation_Amount","Location_Deviation",
    "Device_Change","IP_Risk_Score",
    "Merchant_Change","Payment_Method_Change","Is_Weekend","Is_Night","Fraud"
]

df = pd.DataFrame(rows, columns=columns)
df["Timestamp"] = pd.to_datetime(df["Timestamp"])

# ---------------- SORT ----------------
df["User_Num"] = df["User_ID"].str.extract(r"(\d+)").astype(int)
df.sort_values(by=["User_ID", "Timestamp"], ascending=[True, True], inplace=True)
df.drop(columns=["User_Num"], inplace=True)

# ---------------- COMPUTE FREQUENCY AND AVERAGES ----------------
df["Transaction_Date"] = df["Timestamp"].dt.date
df["Transaction_Frequency"] = df.groupby(["User_ID","Transaction_Date"]).cumcount() + 1
df["Avg_Transaction_Frequency"] = df.groupby("User_ID")["Transaction_Frequency"].expanding().mean().reset_index(level=0, drop=True)
df["Avg_Transaction_Amount"] = df.groupby("User_ID")["Transaction_Amount"].expanding().mean().reset_index(level=0, drop=True)
df["Deviation_Amount"] = abs(df["Transaction_Amount"] - df["Avg_Transaction_Amount"])

# ---------------- DEVICE / MERCHANT / PAYMENT CHANGE ----------------
def _change_last_n(values: pd.Series, n: int = 10) -> pd.Series:
    prev = deque(maxlen=n)
    out = []
    for v in values:
        if len(prev) == 0:
            out.append(0)
        else:
            out.append(0 if v in prev else 1)
        prev.append(v)
    return pd.Series(out, index=values.index)

df["Device_Change"] = (
    df.groupby("User_ID")["Device_Type"]
    .apply(lambda s: _change_last_n(s, 10))
    .reset_index(level=0, drop=True)
)
df["Merchant_Change"] = (
    df.groupby("User_ID")["Merchant_Category"]
    .apply(lambda s: _change_last_n(s, 10))
    .reset_index(level=0, drop=True)
)
df["Payment_Method_Change"] = (
    df.groupby("User_ID")["Payment_Method"]
    .apply(lambda s: _change_last_n(s, 10))
    .reset_index(level=0, drop=True)
)

# ---------------- DROP TEMP ----------------
df.drop(columns=["Transaction_Date"], inplace=True)

# ---------------- FILTER ONLY LEGIT TRANSACTIONS ----------------
df_legit = df[df["Fraud"]==0].copy()
df_legit["Timestamp"] = pd.to_datetime(df_legit["Timestamp"])

# ---------------- RECOMPUTE FREQUENCY FOR LEGIT ONLY ----------------
df_legit["Transaction_Date"] = df_legit["Timestamp"].dt.date
df_legit["Transaction_Frequency"] = df_legit.groupby(["User_ID","Transaction_Date"]).cumcount() + 1
df_legit["Avg_Transaction_Frequency"] = df_legit.groupby("User_ID")["Transaction_Frequency"].expanding().mean().reset_index(level=0, drop=True)
df_legit["Avg_Transaction_Amount"] = df_legit.groupby("User_ID")["Transaction_Amount"].expanding().mean().reset_index(level=0, drop=True)
df_legit["Deviation_Amount"] = abs(df_legit["Transaction_Amount"] - df_legit["Avg_Transaction_Amount"])
# Recompute change flags for legit transactions only (no explicit history columns needed)
df_legit["Device_Change"] = (
    df_legit.groupby("User_ID")["Device_Type"]
    .apply(lambda s: _change_last_n(s, 10))
    .reset_index(level=0, drop=True)
)
df_legit["Merchant_Change"] = (
    df_legit.groupby("User_ID")["Merchant_Category"]
    .apply(lambda s: _change_last_n(s, 10))
    .reset_index(level=0, drop=True)
)
df_legit["Payment_Method_Change"] = (
    df_legit.groupby("User_ID")["Payment_Method"]
    .apply(lambda s: _change_last_n(s, 10))
    .reset_index(level=0, drop=True)
)
df_legit.drop(columns=["Transaction_Date"], inplace=True)

# ---------------- SAVE CSV ----------------
OUTPUT_FILE = "legit_transactions.csv"
output_columns = [
    "User_ID","User_Category","Transaction_Amount","Transaction_Channel",
    "Payment_Method","Timestamp","Merchant_Category","Currency",
    "Device_Type","Device_Location","Transaction_IP_Address_Location",
    "Transaction_Frequency","Avg_Transaction_Amount",
    "Avg_Transaction_Frequency","Deviation_Amount","Location_Deviation",
    "Device_Change","IP_Risk_Score",
    "Merchant_Change","Payment_Method_Change",
    "Is_Weekend","Is_Night","Fraud"
]
df_legit = df_legit[output_columns]
df_legit.to_csv(OUTPUT_FILE, index=False)
print("\nLegit dataset saved:", OUTPUT_FILE)

