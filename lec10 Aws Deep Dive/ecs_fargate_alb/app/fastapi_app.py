"""Milepost's API: resale pricing and a finance pre-check for used cars.

    uvicorn fastapi_app:app --host 0.0.0.0 --port 8000  ->  http://<host>:8000/docs

Two models behind three endpoints: /predict/price, /predict/price/batch and /predict/loan.
Everything between `class PriceRequest` and the route decorators is the contract: a body
that does not match it is refused with a 422 before any model code runs.

`/` and `/health` also report which copy of the service answered (`served_by`): the
availability zone and the ECS task it runs in.
"""

import json
import os
import urllib.request
from pathlib import Path
from typing import Literal

import joblib
import pandas as pd
import sklearn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Read from the environment with a sane default, because that is how configuration
# reaches a container: the image is fixed, the env var is what changes per deployment.
ARTIFACTS = Path(os.getenv("MILEPOST_ARTIFACTS", Path(__file__).parent / "artifacts"))

# The same dictionaries that encoded the columns at training time. If these drift from
# the training code, the models keep answering -- just wrongly.
encode_dict = {
    "fuel_type": {"Diesel": 1, "Petrol": 2, "CNG": 3, "LPG": 4, "Electric": 5},
    "transmission_type": {"Manual": 1, "Automatic": 2},
    "seller_type": {"Dealer": 1, "Individual": 2, "Trustmark Dealer": 3},
}

loan_encode_dict = {
    "Gender": {"Male": 0, "Female": 1},
    "Married": {"No": 0, "Yes": 1},
    "Credit_History": {"Uncleared Debts": 0, "Cleared Debts": 1},
}

PRICE_FEATURES = [
    "year",
    "seller_type",
    "km_driven",
    "fuel_type",
    "transmission_type",
    "mileage",
    "engine",
    "max_power",
    "seats",
]
LOAN_FEATURES = ["Gender", "Married", "ApplicantIncome", "LoanAmount", "Credit_History"]

# A module body runs exactly once per Python process, so these loads happen at import
# time and never again, no matter how many requests follow. Four worker processes means
# four copies of these objects in RAM.
_missing = [
    n
    for n in ("price_model.joblib", "loan_model.joblib", "model_meta.json")
    if not (ARTIFACTS / n).exists()
]
if _missing:
    raise FileNotFoundError(
        f"artifacts/ is missing {_missing}. The image copies them in; check the Dockerfile."
    )

price_model = joblib.load(ARTIFACTS / "price_model.joblib")
loan_model = joblib.load(ARTIFACTS / "loan_model.joblib")
META = json.loads((ARTIFACTS / "model_meta.json").read_text())

# A serving decision, not a modelling one. It lives beside the artifact, versioned
# with the model that calibrated it.
# No fallback: a missing threshold raises here, at import, rather than letting the
# service answer with a cut nobody chose.
THRESHOLD = META["decision_threshold"]
if not 0.0 < THRESHOLD < 1.0:
    raise ValueError(f"decision_threshold {THRESHOLD!r} is not a probability")

MODEL_VERSION = META["model_version"]


def served_by():
    """Ask ECS which availability zone and task this container is running in.

    ECS puts the address of the task metadata endpoint in ECS_CONTAINER_METADATA_URI_V4.
    On a laptop the variable is not set.
    """
    metadata_uri = os.getenv("ECS_CONTAINER_METADATA_URI_V4")
    if not metadata_uri:
        return {"availability_zone": "local", "task_id": "local"}
    try:
        with urllib.request.urlopen(metadata_uri + "/task", timeout=2) as response:
            task = json.load(response)
    except (OSError, ValueError) as exc:
        return {"availability_zone": "unknown", "task_id": f"metadata error: {exc}"}
    # TaskARN looks like arn:aws:ecs:REGION:ACCOUNT:task/CLUSTER/TASK_ID
    return {
        "availability_zone": task["AvailabilityZone"],
        "task_id": task["TaskARN"].split("/")[-1],
    }


# Which copy of the service answered. Asked once, when the process starts.
SERVED_BY = served_by()


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
    """Resale price in lakhs for one car."""
    data = pd.DataFrame(
        [
            [
                float(year),
                encode_dict["seller_type"][seller_type],
                float(km_driven),
                encode_dict["fuel_type"][fuel_type],
                encode_dict["transmission_type"][transmission_type],
                float(mileage),
                float(engine),
                float(max_power),
                float(seats),
            ]
        ],
        columns=PRICE_FEATURES,
    )
    return round(float(price_model.predict(data)[0]), 2)


def loan_pred(Gender, Married, ApplicantIncome, LoanAmount, Credit_History):
    """Finance pre-check for one buyer: (verdict, probability).

    Returns both, because the verdict alone cannot be audited. Six months from now the
    question is "why was this application rejected", and only the probability and the
    cut applied to it can answer that.
    """
    data = pd.DataFrame(
        [
            [
                loan_encode_dict["Gender"][Gender],
                loan_encode_dict["Married"][Married],
                float(ApplicantIncome),
                float(LoanAmount),
                loan_encode_dict["Credit_History"][Credit_History],
            ]
        ],
        columns=LOAN_FEATURES,
    )
    # NOT loan_model.predict(data), which would silently mean THRESHOLD = 0.5.
    probability = float(loan_model.predict_proba(data)[0, 1])
    status = "Loan Approved" if probability >= THRESHOLD else "Loan Rejected"
    return status, probability


app = FastAPI(
    title="Milepost API",
    description="Resale pricing and finance pre-check for used cars.",
    version="1.0.0",
)


# Each annotation below is a sentence about the world, and the framework enforces it on
# every request forever. `Literal[...]` is what makes an unlisted value a 422 instead of
# a KeyError -- or, worse, a default nobody chose.
class PriceRequest(BaseModel):
    year: int = Field(ge=1991, le=2021, description="Manufacturing year")
    seller_type: Literal["Dealer", "Individual", "Trustmark Dealer"]
    km_driven: float = Field(ge=0, le=400_000)
    fuel_type: Literal["Diesel", "Petrol", "CNG", "LPG", "Electric"]
    transmission_type: Literal["Manual", "Automatic"]
    mileage: float = Field(ge=0, le=40, description="kmpl")
    engine: float = Field(ge=500, le=7000, description="cc")
    max_power: float = Field(ge=5, le=650, description="bhp")
    seats: int = Field(ge=2, le=14)


class PriceResponse(BaseModel):
    price_lakhs: float
    model_version: str = Field(description="Which artifact produced this number")


class LoanRequest(BaseModel):
    Gender: Literal["Male", "Female"]
    Married: Literal["Yes", "No"]
    ApplicantIncome: float = Field(ge=0, description="Monthly income")
    LoanAmount: float = Field(ge=0, description="Requested amount, in thousands")
    Credit_History: Literal["Cleared Debts", "Uncleared Debts"]


class LoanResponse(BaseModel):
    # Four fields, not one. The decision is made here so every caller gets the same one;
    # the basis travels with it so a caller that owns lending policy can apply its own
    # cut without us shipping anything.
    loan_approval_status: str = Field(description="The decision this service applied")
    probability: float = Field(description="P(clears debts) from the model")
    threshold_applied: float = Field(description="The cut that produced the decision")
    model_version: str = Field(description="Which artifact produced the probability")


@app.get("/")
def home():
    # Open the service in a browser: this says which copy answered.
    return {"service": "Milepost API", "docs": "/docs", "served_by": SERVED_BY}


@app.get("/health")
def health():
    # Prove the artifacts actually load and score, and answer 503 rather than 200 when
    # they do not, so a load balancer or an orchestrator stops routing here.
    try:
        canary = model_pred(2018, "Dealer", 45000, "Petrol", "Manual", 18.5, 1200, 85.0, 5)
        loan_pred("Male", "No", 5000, 128, "Cleared Debts")
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"{type(exc).__name__}: {exc}"
        ) from exc

    return {
        "status": "ok",
        "models": ["price", "loan"],
        "canary_price_lakhs": canary,
        "decision_threshold": THRESHOLD,
        "model_version": MODEL_VERSION,
        "sklearn_version": sklearn.__version__,
        "sklearn_version_at_train": META["sklearn_version"],
        "served_by": SERVED_BY,
    }


# Plain `def`, not `async def`: these handlers are CPU work with no `await` in them.
# FastAPI runs a `def` handler in a threadpool, so it cannot block the event loop.
@app.post("/predict/price", response_model=PriceResponse)
def predict_price(req: PriceRequest):
    # If the body did not match PriceRequest, this line never executed.
    price = model_pred(
        req.year,
        req.seller_type,
        req.km_driven,
        req.fuel_type,
        req.transmission_type,
        req.mileage,
        req.engine,
        req.max_power,
        req.seats,
    )
    return PriceResponse(price_lakhs=price, model_version=MODEL_VERSION)


@app.post("/predict/price/batch", response_model=list[PriceResponse])
def predict_price_batch(cars: list[PriceRequest]):
    """Many cars, one HTTP round trip and one vectorised predict."""
    # `list[PriceRequest]` is the whole validation story: FastAPI checks every element
    # and refuses the entire body if one of them is wrong, before this line runs. The
    # two guards below are the only hand-written error handling in this file.
    if not cars:
        raise HTTPException(status_code=422, detail="send at least one car")
    if len(cars) > 1000:
        raise HTTPException(status_code=413, detail="at most 1000 cars per call")

    # One frame, one predict. Vectorising is not a FastAPI feature -- either framework
    # could do it -- but a loop is what gets written first in both.
    frame = pd.DataFrame(
        [
            [
                float(c.year),
                encode_dict["seller_type"][c.seller_type],
                float(c.km_driven),
                encode_dict["fuel_type"][c.fuel_type],
                encode_dict["transmission_type"][c.transmission_type],
                float(c.mileage),
                float(c.engine),
                float(c.max_power),
                float(c.seats),
            ]
            for c in cars
        ],
        columns=PRICE_FEATURES,
    )
    return [
        PriceResponse(price_lakhs=round(float(p), 2), model_version=MODEL_VERSION)
        for p in price_model.predict(frame)
    ]


@app.post("/predict/loan", response_model=LoanResponse)
def predict_loan(req: LoanRequest):
    # No if/else chain, because there is nothing left to guess about. Every field
    # arrived typed, in range, and spelled one of the ways the model was trained on.
    status, probability = loan_pred(
        req.Gender,
        req.Married,
        req.ApplicantIncome,
        req.LoanAmount,
        req.Credit_History,
    )
    return LoanResponse(
        loan_approval_status=status,
        probability=round(probability, 4),
        threshold_applied=THRESHOLD,
        model_version=MODEL_VERSION,
    )
