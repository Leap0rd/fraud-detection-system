# Fraud Detection System

An intelligent fraud detection system using autoencoder-based anomaly detection with adaptive learning capabilities.

## Features

- **Real-time Fraud Detection**: Processes transactions in <1 second
- **Autoencoder Architecture**: Deep neural network for pattern recognition
- **Adaptive Learning**: Automatic model retraining every 5 legitimate transactions
- **Personalized Thresholds**: User-specific fraud thresholds after 100 transactions
- **Explainable AI**: Feature importance explanations for fraud decisions
- **Location-based Detection**: Flags transactions with location mismatches
- **Real-time Dashboard**: React-based monitoring interface

## Architecture

- **Backend**: Flask API with TensorFlow/Keras
- **Frontend**: React dashboard with real-time updates
- **ML Model**: Deep dense autoencoder (64-32-16-32-64-input_dim)
- **Database**: JSON-based storage for thresholds and logs

## Project Structure

```
FYP-2/
├── Flask_api.py              # Main API server
├── train.py                  # Model training script
├── dataset.py                # Data generation utilities
├── test_model.py             # Testing script
├── fraud-detection-dashboard/ # React frontend
├── requirements.txt          # Python dependencies
└── README.md                # This file
```

## Installation

1. Clone the repository
2. Create virtual environment:
   ```bash
   python -m venv myenv
   source myenv/bin/activate  # On Windows: myenv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Train the model:
   ```bash
   python train.py
   ```
5. Start the API server:
   ```bash
   python Flask_api.py
   ```
6. Run the frontend:
   ```bash
   cd fraud-detection-dashboard
   npm install
   npm start
   ```

## API Endpoints

- `POST /predict` - Process transaction and detect fraud
- `GET /stats` - Get system statistics
- `GET /logs` - Get transaction history

## Usage

### Test with Sample Transaction
```python
import requests

transaction = {
    "User_ID": "U1",
    "User_Category": "regular",
    "Transaction_Amount": 2300.21,
    "Transaction_Channel": "utility_bill_payment",
    "Payment_Method": "sadapay",
    "Timestamp": "2025-07-23 19:30:24",
    "Merchant_Category": "utilities",
    "Currency": "PKR",
    "Device_Type": "mobile",
    "Device_Location": "Karachi",
    "Transaction_IP_Address_Location": "Karachi",
    "Transaction_Frequency": 1,
    "IP_Risk_Score": "low",
    "Is_Weekend": 0,
    "Is_Night": 0
}

response = requests.post("http://localhost:5000/predict", json={"transaction": transaction})
result = response.json()
```

## Features Explained

### Transaction Features (23 total)
- **Basic Info**: User_ID, Amount, Channel, Payment Method, etc.
- **Behavioral**: Avg transaction amount/frequency, deviations
- **Location**: Device vs IP location comparison
- **Risk**: IP risk score, device changes, timing patterns

### Detection Methods
- **Reconstruction Error**: Autoencoder identifies anomalies
- **Threshold Comparison**: Personalized vs category thresholds
- **Rule-based**: Location deviation for new users
- **Adaptive Learning**: Continuous model improvement

## Performance

- **Processing Time**: <1 second per transaction
- **False Positive Rate**: ~5% on legitimate transactions
- **Model Accuracy**: 95th percentile threshold for fraud detection
- **Adaptation Speed**: Every 5 legitimate transactions

## Technologies Used

- **Backend**: Python, Flask, TensorFlow/Keras, Pandas, Scikit-learn
- **Frontend**: React, TypeScript, TailwindCSS
- **ML**: Autoencoder neural networks, unsupervised learning
- **Data**: JSON, CSV files

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is for educational purposes as part of a Final Year Project (FYP).
