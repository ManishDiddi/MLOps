"""Let the real-time endpoint add a second machine when traffic per machine passes a target."""
import boto3

ENDPOINT = "leviathan-xgb-rt"
RESOURCE = f"endpoint/{ENDPOINT}/variant/AllTraffic"

scaling = boto3.client("application-autoscaling")

# The range the endpoint may move in. It never goes below 1 or above 2 machines.
scaling.register_scalable_target(
    ServiceNamespace="sagemaker",
    ResourceId=RESOURCE,
    ScalableDimension="sagemaker:variant:DesiredInstanceCount",
    MinCapacity=1,
    MaxCapacity=2,
)

# Target tracking: keep each machine near 300 requests a minute, adding or removing machines to stay there.
scaling.put_scaling_policy(
    PolicyName="leviathan-xgb-rt-invocations",
    ServiceNamespace="sagemaker",
    ResourceId=RESOURCE,
    ScalableDimension="sagemaker:variant:DesiredInstanceCount",
    PolicyType="TargetTrackingScaling",
    TargetTrackingScalingPolicyConfiguration={
        "TargetValue": 300.0, # 300 requests per minute per machine
        "PredefinedMetricSpecification": {"PredefinedMetricType": "SageMakerVariantInvocationsPerInstance"},
        "ScaleOutCooldown": 60,
        "ScaleInCooldown": 300,
    },
)

for target in scaling.describe_scalable_targets(ServiceNamespace="sagemaker", ResourceIds=[RESOURCE])["ScalableTargets"]:
    print("scalable target:", target["ResourceId"], "min", target["MinCapacity"], "max", target["MaxCapacity"])
alarms = scaling.describe_scaling_policies(ServiceNamespace="sagemaker", ResourceId=RESOURCE)["ScalingPolicies"][0]["Alarms"]
for alarm in alarms:
    print("alarm AWS created for the policy:", alarm["AlarmName"])