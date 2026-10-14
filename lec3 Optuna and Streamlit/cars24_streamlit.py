import streamlit as st
import pandas as pd
import numpy as np
import joblib
import pickle
from pathlib import Path
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).parent


st.title("Cars24 Used Car Price Prediction")

year = st.slider(
    "Manufacturing Year", min_value=1990, max_value=2023, value=2015, step=1
)
seller_type = st.selectbox("Seller Type", ["Dealer", "Individual", "Trustmark Dealer"])

col1, col2 = st.columns(2)

with col1:
    fuel_type = st.selectbox("Fuel Type", ["Diesel", "Petrol", "CNG", "LPG", "Electric"])
    max_power = st.number_input(
"Max Power (bhp)", min_value=0.0, max_value=300.0, value=150.0, step=5.0
)

with col2:
    engine = st.number_input(
        "Engine (cc)", min_value=500, max_value=5000, value=1500, step=100
    )
    km_driven = st.number_input(
    "Kilometers Driven", min_value=0, max_value=1000000, value=50000, step=5000
)

mileage = st.number_input(
    "Mileage (kmpl)", min_value=0.0, max_value=18.0, value=15.0, step=0.5
)


transmission_type = st.selectbox("Transmission Type", ["Manual", "Automatic"])

seats = st.number_input("Seats", min_value=2, max_value=10, value=5, step=1)

# Load the trained model and scaler from this file's folder (Streamlit Cloud runs the app from the repo root)
model = joblib.load(HERE / "cars24_model.joblib")
scaler = joblib.load(HERE / "scaler.pkl")

#with open(HERE / "cars24_model.pkl", "rb") as f:
#	model = pickle.load(f)

#with open(HERE / "scaler.pkl", "rb") as f:
#	scaler = pickle.load(f)

# Create a pipeline that combines scaling and prediction
pipeline = Pipeline([("scaler", scaler), ("model", model)])


encode_dict = {
    "fuel_type": {"Diesel": 1, "Petrol": 2, "CNG": 3, "LPG": 4, "Electric": 5},
    "transmission_type": {"Manual": 1, "Automatic": 2},
    "seller_type": {"Dealer": 1, "Individual": 2, "Trustmark Dealer": 3},
}


def model_pred(
    year,
    seller_type,
    km_driven,
    fuel_type,
    transmission_type,
    mileage,
    engine,
    max_power,
    seats,
):
    # Convert categorical features using the encode dictionary
    seller_type_enc = encode_dict["seller_type"][seller_type]
    fuel_type_enc = encode_dict["fuel_type"][fuel_type]
    transmission_type_enc = encode_dict["transmission_type"][transmission_type]

    # Prepare input data
    data = [
        [
            float(year),
            seller_type_enc,
            float(km_driven),
            fuel_type_enc,
            transmission_type_enc,
            float(mileage),
            float(engine),
            float(max_power),
            float(seats),
        ]
    ]

    # Use pipeline for prediction (handles scaling automatically)
    prediction = pipeline.predict(data)

    return round(prediction[0], 2)


if st.button("Predict"):
    price = model_pred(
        year,
        seller_type,
        km_driven,
        fuel_type,
        transmission_type,
        mileage,
        engine,
        max_power,
        seats,
    )

    st.write(f"**Predicted Car Price**: {price} Lakhs (approx.)")
else:
    st.write("Click the **Predict** button once you've entered all the details.")
