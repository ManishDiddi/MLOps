"""Call the real-time endpoint with a few held-back orders, then with three broken rows."""
import time

import boto3
import pandas as pd

from config import BUCKET

s3 = boto3.client("s3")
runtime = boto3.client("sagemaker-runtime")
ENDPOINT = "leviathan-xgb-rt"

rows = pd.read_csv(s3.get_object(Bucket=BUCKET, Key="batch-input/batch.csv")["Body"], header=None)
labels = pd.read_csv(s3.get_object(Bucket=BUCKET, Key="batch-labels/labels.csv")["Body"])["returned"]


def call(body):
    response = runtime.invoke_endpoint(EndpointName=ENDPOINT, ContentType="text/csv", Body=body)
    return float(response["Body"].read())


for i in range(5):
    body = ",".join(str(v) for v in rows.iloc[i].values)
    start = time.time()
    p = call(body)
    print(f"p(return)={p:.3f}  actual={labels.iloc[i]}  {round((time.time() - start) * 1000)} ms")

good = rows.iloc[0].tolist()
broken = {
    "one feature too many": good + [1],
    "price left out": good[1:],
    "a raw category value": ["apparel"] + good[1:],
}
print()
print(f"{'correct row':22s} -> p(return)={call(','.join(map(str, good))):.3f}")
for name, values in broken.items():
    try:
        p = call(",".join(map(str, values)))
        print(f"{name:22s} -> ACCEPTED, p(return)={p:.3f}")
    except runtime.exceptions.ModelError as e:
        print(f"{name:22s} -> ModelError: {str(e)[:160]}")