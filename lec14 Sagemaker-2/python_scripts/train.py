"""Start a SageMaker training job with the built-in XGBoost container."""
from sagemaker.core import image_uris
from sagemaker.core.helper.session_helper import get_execution_role
from sagemaker.core.training.configs import Compute, InputData, OutputDataConfig
from sagemaker.train import ModelTrainer

from config import BUCKET, REGION

image = image_uris.retrieve("xgboost", REGION, "1.7-1")
print("image:", image)

trainer = ModelTrainer(
    training_image=image,
    role=get_execution_role(),
    base_job_name="leviathan-xgb",
    compute=Compute(instance_type="ml.m5.large", instance_count=1, volume_size_in_gb=5),
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

job = trainer._latest_training_job  # the TrainingJob the SDK just ran
print("job:", job.training_job_name, job.training_job_status)
print("billable seconds:", job.billable_time_in_seconds)
print("final metrics:", {m.metric_name: round(m.value, 3) for m in job.final_metric_data_list})
print("model:", job.model_artifacts.s3_model_artifacts)