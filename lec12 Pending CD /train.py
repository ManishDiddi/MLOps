"""Trains classifier.pkl, the loan-approval model that hello.py serves.

    python train.py

Change the model here, retrain, and open a pull request: the model gate in CI
scores the new classifier.pkl against the one on master.
"""
import joblib
import pandas as pd
from sklearn import linear_model

train_df = pd.read_csv('train_flask.csv')

train_df['Gender'] = train_df['Gender'].map({'Male': 0, 'Female': 1})
train_df['Married'] = train_df['Married'].map({'No': 0, 'Yes': 1})
train_df['Loan_Status'] = train_df['Loan_Status'].map({'N': 0, 'Y': 1})

## dropping all the missing values
train_df = train_df.dropna()

X = train_df[['Gender', 'Married', 'ApplicantIncome', 'LoanAmount', 'Credit_History']]
y = train_df.Loan_Status

model = linear_model.LogisticRegression()
model.fit(X, y)

joblib.dump(model, 'classifier.pkl')
print(f"trained on {len(y)} applications, wrote classifier.pkl")
