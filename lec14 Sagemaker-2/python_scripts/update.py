"""Move the real-time endpoint to a new model blue/green, and roll back by itself on errors."""
import sys
import threading
import time

import boto3
from sagemaker.core import image_uris
from sagemaker.core.helper.session_helper import get_execution_role
from sagemaker.core.resources import Endpoint, EndpointConfig, Model
from sagemaker.core.shapes import (Alarm, AutoRollbackConfig, BlueGreenUpdatePolicy,
                                   ContainerDefinition, DeploymentConfig, ProductionVariant,
                                   TrafficRoutingConfig)

from config import REGION

MODEL_DATA = sys.argv[1]  # the new model.tar.gz, from train_spot.py
ENDPOINT = "leviathan-xgb-rt"
ALARM = "leviathan-xgb-rt-5xx"

model = Model.create(
    model_name="leviathan-xgb-model-v3",
    primary_container=ContainerDefinition(image=image_uris.retrieve("xgboost", REGION, "1.7-1"),
                                          model_data_url=MODEL_DATA),
    execution_role_arn=get_execution_role(),
)
config = EndpointConfig.create(
    endpoint_config_name="leviathan-xgb-rt-config-v3",
    production_variants=[ProductionVariant(variant_name="AllTraffic", model_name=model.model_name,
                                           instance_type="ml.m5.large", initial_instance_count=1)],
)

# The alarm that decides a rollback: any server error from the endpoint in a minute.
boto3.client("cloudwatch").put_metric_alarm(
    AlarmName=ALARM, Namespace="AWS/SageMaker", MetricName="Invocation5XXErrors",
    Dimensions=[{"Name": "EndpointName", "Value": ENDPOINT}, {"Name": "VariantName", "Value": "AllTraffic"}],
    Statistic="Sum", Period=60, EvaluationPeriods=1, Threshold=0,
    ComparisonOperator="GreaterThanThreshold", TreatMissingData="notBreaching",
)

# Keep calling the endpoint the whole time, the way real users would.
runtime = boto3.client("sagemaker-runtime")
row = "14955.0,12,5,902,12,2,0,3.4,0,0,0,1,0,0,1,0,0,0"  # the first order in batch.csv
calls = {"ok": 0, "failed": 0}
done = threading.Event()

def traffic():
    while not done.is_set():
        try:
            runtime.invoke_endpoint(EndpointName=ENDPOINT, ContentType="text/csv", Body=row)["Body"].read()
            calls["ok"] += 1
        except Exception:
            calls["failed"] += 1
        time.sleep(0.5)

threading.Thread(target=traffic, daemon=True).start()

endpoint = Endpoint.get(ENDPOINT)

print("serving before:", endpoint.endpoint_config_name)

endpoint.endpoint_config_name = config.endpoint_config_name

endpoint.update(
    deployment_config=DeploymentConfig(
        blue_green_update_policy=BlueGreenUpdatePolicy(
            traffic_routing_configuration=TrafficRoutingConfig(
                type="ALL_AT_ONCE",
                wait_interval_in_seconds=120,
            ),
            termination_wait_in_seconds=180,
        ),
        auto_rollback_configuration=AutoRollbackConfig(
            alarms=[Alarm(alarm_name=ALARM)]
        ),
    )
)

sm = boto3.client("sagemaker")
start, last = time.time(), None
while True:
    d = sm.describe_endpoint(EndpointName=ENDPOINT)
    pending = d.get("PendingDeploymentSummary", {}).get("ProductionVariants", [])
    stage = pending[0].get("VariantStatus", [{}])[0].get("Status", "-") if pending else "-"
    now = (d["EndpointStatus"], stage)
    if now != last:
        print(f"after {round(time.time() - start)} s: endpoint {now[0]}, new fleet {now[1]}")
        last = now
    if d["EndpointStatus"] in {
    "InService",
    "Failed",
    "UpdateRollbackFailed"
    }:
        break
    
    time.sleep(10)
done.set()

print("serving after:", d["EndpointConfigName"])
print(f"calls during the update: {calls['ok']} answered, {calls['failed']} failed")