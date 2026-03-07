import requests
import matplotlib.pyplot as plt
import textwrap

url = "http://127.0.0.1:5000/predict"

# ----------------------------
# 1. Two transactions
# ----------------------------
transactions = [
    {
        "User_ID": "U1",
        "User_Category": "regular",
        "Transaction_Amount": 230000.21,
        "Transaction_Channel": "utility_bill_payment",
        "Payment_Method": "sadapay",
        "Timestamp": "2025-07-23 19:30:24",
        "Merchant_Category": "utilities",
        "Currency": "PKR",
        "Device_Type": "mobile",
        "Device_Location": "Lahore",
        "Transaction_IP_Address_Location": "Karachi",
        "Transaction_Frequency": 1,
        "IP_Risk_Score": "high",
        "Is_Weekend": 0,
        "Is_Night": 0
    },
    # {
    #     "User_ID": "U1",
    #     "User_Category": "regular",
    #     "Transaction_Amount": 95000.00,
    #     "Transaction_Channel": "online_purchase",
    #     "Payment_Method": "credit_card",
    #     "Timestamp": "2025-07-23 02:10:00",
    #     "Merchant_Category": "electronics",
    #     "Currency": "PKR",
    #     "Device_Type": "xyz",
    #     "Device_Location": "Karachi",
    #     "Transaction_IP_Address_Location": "Lahore",
    #     "Transaction_Frequency": 3,
    #     "IP_Risk_Score": "high",
    #     "Is_Weekend": 0,
    #     "Is_Night": 1
    # }
]

# ----------------------------
# 2. Send transactions one by one
# ----------------------------
for i, transaction in enumerate(transactions, start=1):
    print(f"\n--- Sending Transaction {i} ---")

    payload = {"transaction": transaction}

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        continue

    result = response.json()

    # ----------------------------
    # 3. Ask confirmation if suspicious
    # ----------------------------
    confirm = False
    if result["is_anomaly"]:
        confirm = input(
            "Transaction looks suspicious. Is this transaction legitimate? (y/n): "
        ).strip().lower() == "y"

        if confirm:
            payload["confirm"] = True
            response = requests.post(url, json=payload)
            result = response.json()

    # ----------------------------
    # 4. Display result
    # ----------------------------
    print("User ID:", transaction["User_ID"])
    print(f"Reconstruction Error: {result['reconstruction_error']:.6f}")
    status = "FRAUDULENT" if result["is_anomaly"] and not confirm else "Normal"
    print("Transaction Status:", status)
    print(f"Threshold Used: {result['threshold_used']:.6f}")

    # ----------------------------
    # 5. Plot XAI
    # ----------------------------
    if result.get("top_features"):
        names, values = zip(*result["top_features"])
        wrapped_names = ["\n".join(textwrap.wrap(n, 20)) for n in names]

        plt.figure(figsize=(10, 6))
        plt.barh(wrapped_names, values)
        plt.gca().invert_yaxis()
        plt.title("Top Contributing Features")
        plt.tight_layout()
        plt.show()
