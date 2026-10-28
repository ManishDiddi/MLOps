"""Serve the trained model on a real-time endpoint: a model, a configuration, then the endpoint."""
import sys
import time

from sagemaker.core import image_uris
from sagemaker.core.helper.session_helper import get_execution_role
from sagemaker.core.resources import Endpoint, EndpointConfig, Model
from sagemaker.core.shapes import ContainerDefinition, ProductionVariant

from config import REGION

MODEL_DATA = sys.argv[1]  # the s3://.../model.tar.gz that train.py printed

model = Model.create(
    model_name="leviathan-xgb-model",
    primary_container=ContainerDefinition(
        image=image_uris.retrieve("xgboost", REGION, "1.7-1"),
        model_data_url=MODEL_DATA,
    ),
    execution_role_arn=get_execution_role(),
)
print("model:", model.model_name)

config = EndpointConfig.create(
    endpoint_config_name="leviathan-xgb-rt-config",
    production_variants=[ProductionVariant(
        variant_name="AllTraffic",
        model_name=model.model_name,
        instance_type="ml.m5.large",
        initial_instance_count=1,
    )],
)

# m1 - lightgbm - 0.8
# m2 - log-reg - 0.75


#config = EndpointConfig.create(
#    endpoint_config_name="leviathan-xgb-rt-config",
#    production_variants=[
#        ProductionVariant(
#            variant_name="ModelA",
#            model_name=model_a.model_name,
#            instance_type="ml.m5.large",
#            initial_instance_count=1,
#            initial_variant_weight=0.8,
#        ),
#        ProductionVariant(
#            variant_name="ModelB",
#            model_name=model_b.model_name,
#            instance_type="ml.m5.large",
#            initial_instance_count=1,
#            initial_variant_weight=0.2,
#        ),
#    ],
#)
print("endpoint config:", config.endpoint_config_name)

start = time.time()
endpoint = Endpoint.create(endpoint_name="leviathan-xgb-rt", endpoint_config_name=config.endpoint_config_name)
endpoint.wait_for_status("InService")
print("endpoint:", endpoint.endpoint_name, "InService after", round(time.time() - start), "s")