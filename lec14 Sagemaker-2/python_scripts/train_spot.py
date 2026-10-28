"""The same training job on spare (spot) capacity, with checkpoints and cost tags."""
from sagemaker.core import image_uris
from sagemaker.core.helper.session_helper import get_execution_role
from sagemaker.core.training.configs import (CheckpointConfig, Compute, InputData,
                                             OutputDataConfig, StoppingCondition, Tag)
from sagemaker.train import ModelTrainer

from config import BUCKET, REGION

trainer = ModelTrainer(
    training_image=image_uris.retrieve("xgboost", REGION, "1.7-1"),
    role=get_execution_role(),
    base_job_name="leviathan-xgb-spot",
    compute=Compute(instance_type="ml.m5.large", instance_count=1, volume_size_in_gb=5,
                    enable_managed_spot_training=True),
    # Spot needs a second limit: how long to wait for spare capacity plus the training itself.
    stopping_condition=StoppingCondition(max_runtime_in_seconds=3600, max_wait_time_in_seconds=7200),
    # If AWS takes the machine back, the job restarts from the last checkpoint, not from zero.
    checkpoint_config=CheckpointConfig(s3_uri=f"s3://{BUCKET}/checkpoints/leviathan-xgb-spot/"),
    tags=[Tag(key="project", value="leviathan"), Tag(key="stage", value="experiment")],
    hyperparameters={
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "num_round": 200,
        "eta": 0.1,
        "max_depth": 4,
    },
    output_data_config=OutputDataConfig(s3_output_path=f"s3://{BUCKET}/output/"),
)

trainer.train(
    input_data_config=[
        InputData(channel_name="train", data_source=f"s3://{BUCKET}/train/", content_type="text/csv"),
        InputData(channel_name="validation", data_source=f"s3://{BUCKET}/validation/", content_type="text/csv"),
    ],
    wait=True,
    logs=False,
)

job = trainer._latest_training_job
trained, billed = job.training_time_in_seconds, job.billable_time_in_seconds
print("job:", job.training_job_name, job.training_job_status)
print("training seconds:", trained, " billable seconds:", billed)
print(f"saving from spot: {100 * (1 - billed / trained):.0f}%")
print("final metrics:", {m.metric_name: round(m.value, 3) for m in job.final_metric_data_list})
print("model:", job.model_artifacts.s3_model_artifacts)