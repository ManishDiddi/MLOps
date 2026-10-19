"""The model gate. Scores this change's classifier.pkl against the one on master.

    python evaluate.py

Both models are scored on train_flask.csv, the same loan applications the model
was trained on. (A real gate scores data that no model was ever trained on.)
The change passes only if its model clears two floors and is no worse than
master's. Exits 1 if it does not, which fails the CI job.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import joblib
import pandas as pd

ACCURACY_FLOOR = 0.80      # today's model agrees with 80.8% of the bank's decisions
REJECTIONS_FLOOR = 0.40    # and rejects 42.6% of the applications the bank rejected
MAX_ACCURACY_DROP = 0.01   # a new model may not score lower than master's by more than this


def load_from_master():
    """master's classifier.pkl, read out of Git without touching the working tree."""
    # ./ means "this folder", so the path works whatever the app's folder is called
    blob = subprocess.run(["git", "show", "origin/master:./lec9_CI/classifier.pkl"],
                          capture_output=True, check=True).stdout
    path = Path(tempfile.mkdtemp()) / "classifier.pkl"
    path.write_bytes(blob)
    return joblib.load(path)


def score(model, X, y):
    approved = model.predict(X) == 1
    return {"accuracy": (approved == (y == 1)).mean(),   # agrees with the bank's decision
            "rejections": (~approved[y == 0]).mean(),    # of the bank's rejections, the share the model also rejects
            "approved": approved.mean()}                 # share of all applications the model approves


def main():
    # The same preparation as train.py
    train_df = pd.read_csv('lec12 Pending CD /train_flask.csv')
    train_df['Gender'] = train_df['Gender'].map({'Male': 0, 'Female': 1})
    train_df['Married'] = train_df['Married'].map({'No': 0, 'Yes': 1})
    train_df['Loan_Status'] = train_df['Loan_Status'].map({'N': 0, 'Y': 1})
    train_df = train_df.dropna()
    X = train_df[['Gender', 'Married', 'ApplicantIncome', 'LoanAmount', 'Credit_History']]
    y = train_df.Loan_Status.to_numpy()

    new = joblib.load('lec9_CI/classifier.pkl')
    old = load_from_master()
    a, b = score(old, X, y), score(new, X, y) # old refers to model currently on master, new refers to the model in this change

    lines = [f"| train_flask.csv, {len(y)} applications | master | this change |", "|---|---|---|",
             f"| accuracy | {a['accuracy']:.3f} | {b['accuracy']:.3f} |",
             f"| rejections caught | {a['rejections']:.3f} | {b['rejections']:.3f} |",
             f"| applications approved | {a['approved']:.1%} | {b['approved']:.1%} |"]

    checks = [(b["accuracy"] >= ACCURACY_FLOOR, f"accuracy {b['accuracy']:.3f}, floor {ACCURACY_FLOOR}"),
              (b["rejections"] >= REJECTIONS_FLOOR, f"rejections caught {b['rejections']:.3f}, floor {REJECTIONS_FLOOR}"),
              (a["accuracy"] - b["accuracy"] <= MAX_ACCURACY_DROP,
               f"accuracy {b['accuracy'] - a['accuracy']:+.3f} against master's, may not drop more than {MAX_ACCURACY_DROP}")]
    lines += [""] + [f"- {'✅' if ok else '❌'} {text}" for ok, text in checks]
    report = "\n".join(lines)
    print(report)
    # On GitHub the same table becomes the job's summary page.
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("## Model gate\n\n" + report + "\n")
    if not all(ok for ok, _ in checks):
        sys.exit(1)


if __name__ == "__main__":
    main()
