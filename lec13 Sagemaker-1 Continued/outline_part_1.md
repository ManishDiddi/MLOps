# AWS SageMaker — Part 1: Private Platform and Data


## Objective

The class already knows VPCs, security groups, route tables, internet gateways, S3, and how to run a basic SageMaker notebook/XGBoost experiment. **Today's progression is from “we can train a model” to “we can build a private, usable ML platform and deliver trustworthy training files.”**

**Scenario:** An online store needs to predict at checkout whether an order will be returned. It has `returns.csv`: 12,000 synthetic order records, 14 columns, label `returned`. Today's output is the secure development environment plus four prepared S3 objects; the model is trained in the **next** class.

**One useful opening question:** “Last class, we trained a model. What changes if five engineers need to work on confidential customer data, remotely, with repeatable data preparation and without exposing a public server?”

## Detailed section list — in notebook order

### 0. Preface / recap — Why today is different
- **Existing skills to reconnect:** VPC, subnet, route table, internet gateway, SG, S3, manual SageMaker notebook, XGBoost container.
- **Today's two hats:** *platform engineer* (network, role, Studio domain) then *ML engineer* (remote VS Code, exploration, data preparation).
- **Operating rule:** This notebook is a copy/paste guide for multiple destinations, **not** a notebook to execute with “Run all”. Read each destination label before copying commands, JSON, or code.
- **Transition:** “First, let's see where today's work sits in the complete ML lifecycle.”

### 1. Where SageMaker fits
**Notebook:** §1 and §1.1.
- Recall the earlier SageMaker XGBoost training exercise and contrast ad hoc experimentation with a repeatable team platform.
- Lifecycle picture: `S3 -> training job -> S3 model.tar.gz -> inference (real-time / serverless / batch)`.
- What SageMaker manages (training/inference compute) versus what **we** must still manage (data, IAM, VPC, input formats).
- Briefly locate SageMaker Studio, Domains, Canvas, Training jobs and Inference in the console.
- Project data: return prediction as binary classification; order-time features versus the `returned` target.
- **Ask:** “Where should training data and the finished model live if training instances are temporary?”
- **Outcome:** Learners can explain what is happening **today** versus **next class**.

### 2. What this costs, and what keeps billing
**Notebook:** §2.
- Differentiate billed *while running* (JupyterLab compute; Canvas workspace) from billed *while provisioned* (regional NAT gateway; interface endpoints).
- Preview next class's training job, batch job and real-time endpoint cost behavior.
- AWS Budget alert; identify cleanup actions in advance.
- **Ask:** “Does closing a browser tab necessarily stop the underlying AWS resource?” (No.)
- **Outcome:** Learners know the shutdown obligations before creating anything. **Pricing varies; the notebook's prices are time-/region-specific examples.**

### 3. S3, the place everything meets
**Notebook:** §3 and §3.1.
- S3 bucket versus object; ‘folder’ versus **prefix** (`train/`, `validation/`, etc.).
- Create a uniquely named bucket; keep **Block Public Access** enabled.
- Upload `returns.csv` to `raw/returns.csv`.
- Discuss expected storage lifecycle: `raw/`, `train/`, `validation/`, `batch-input/`, `batch-labels/`, `output/`, `batch-output/`.
- **Ask:** “Why don't we leave the only copy of the dataset inside the SageMaker machine?”
- **Checkpoint:** Locate `s3://<bucket>/raw/returns.csv` and save the bucket name for `config.py`.

### 4. A private network for SageMaker
**Notebook:** §4, §4.1, §4.2, §4.3, §4.4 and Checkpoint 4.1.

**4.1 — Build the VPC and its outbound paths (AWS console)**
- `returns-ml-vpc`, `10.0.0.0/16`, two private subnets across two AZs; no public subnets in this lab.
- Regional NAT gateway for outbound internet access, with its internet gateway path.
- S3 **gateway endpoint** for S3 traffic; understand `local`, S3-prefix-list and `0.0.0.0/0` routes.
- Both VPC DNS settings; zone IDs versus account-specific zone letters.
- **Contrast:** `pip install` goes through NAT, `boto3 -> S3` goes through the gateway endpoint.

**4.2 — Two security groups (AWS console)**
- `returns-studio-sg`: allows app-to-app inbound TCP from itself.
- `returns-endpoints-sg`: allows inbound HTTPS 443 from Studio SG onto endpoint ENIs.
- Explain that network permission and IAM permission are different.

**4.3 — Interface endpoints and private DNS (AWS console + CloudShell)**
- Create `sagemaker.api` manually with private DNS enabled.
- Create **five more** with the supplied CloudShell script: `sagemaker.runtime`, `sts`, `logs`, `ssm`, `ssmmessages`.
- Count: six **interface** endpoints + one S3 **gateway** endpoint = seven.
- Explain an interface endpoint as private access to a service through ENIs in the subnets.

“The network is ready. But what permits the workspace to read the bucket?”

### 5. A role, a domain, and VS Code in a space
**Notebook:** §5.1–5.5.

**5.1 — IAM execution role (AWS console)**
- Create `returns-ml-sagemaker-role` for SageMaker execution.
- Policies: `AmazonSageMakerFullAccess`, `AmazonSageMakerCanvasFullAccess`, `AmazonSageMakerCanvasDataPrepFullAccess`.
- Custom S3 inline policy: distinguish **bucket ARN** permissions from **object ARN (`/*`)** permissions.
- Custom remote-access inline policy: `sagemaker:StartSession`.
- Emphasize credential-free scripts using the assigned role rather than hard-coded access keys.
- **Ask:** “If the security group allows HTTPS, can we read any S3 bucket?” (No, IAM still applies.)

**5.2 — SageMaker Studio domain (AWS console)**
- Create domain with **Set up for organizations** rather than default quick setup.
- `returns-ml-domain`; user profile `instructor`; existing execution role; **VPC only**; two private subnets + Studio SG.
- JupyterLab idle timeout = 60 minutes; Home EFS not needed for this exercise.
- Distinguish **domain**, **user profile**, **Studio**, and **space**.

**5.3 — Private JupyterLab space (Studio)**
- Create `returns-lab` and choose `ml.m5.large`; enable **Remote access**, run the space.
- Explain machine lifecycle versus persistent space files.

**5.4 — Laptop prerequisites (local terminal; ideally preflight before class)**
- VS Code version/`code` command, AWS Toolkit extension, Remote - SSH extension, Session Manager plugin, SSH client.
- These are *connection dependencies*, not the main conceptual content.

**5.5 — Connect VS Code to the running space**
- Studio **Open in VS Code** -> session through AWS Systems Manager (`ssm`, `ssmmessages`); no public SSH listener.
- Run `mkdir -p ~/returns-ml` and open `/home/sagemaker-user/returns-ml`.
- **Critical distinction:** the editor UI is on the laptop; the files, terminal and Python process are on the remote SageMaker space.
- **Checkpoint:** Ask where `python explore.py` executes and why no static AWS key is required.
- **Transition:** “Now we have a secure workspace. We can finally inspect the data.”

### 6. A first look at the data
**Notebook:** §6, §6.1 and Checkpoint 6.1.
- In remote VS Code create `config.py`; set the correct `BUCKET` and `REGION`.
- Create and run `explore.py`; use `boto3.client('s3').get_object(...)` and pandas to read the object body.
- Inspect `(12000, 14)`, return rate **22.8%**, and **502** missing `seller_rating` entries.
- Contrast diagnostic AUC using **scikit-learn `HistGradientBoostingClassifier`**:
  - With `refund_amount`: **1.000**.
  - Without `refund_amount`: **0.706**.
- Teach **target leakage**: refunds happen after return processing; they are unavailable at checkout.
- Do **not** describe this quick diagnostic as the later managed XGBoost training job.
- **Checkpoint 6.1:** Is `delivery_days` a *promise/estimate* or *realized delivery time*? Validate feature availability at prediction time.
- **Transition:** “Can a visual tool detect the same issue without us writing Python?”

### 7. Data Wrangler in Canvas
**Notebook:** §7 and §7.1.
- Open **Canvas** from Studio; enter **Data Wrangler**.
- Import `raw/returns.csv` from S3 as tabular data; open the data flow.
- **Get data insights:** choose target `returned`, classification; review inferred types, missingness, feature power and warnings.
- See `refund_amount` flagged as **High target leakage**.
- Clarify Canvas/Data Wrangler's use case: quick, visual discovery versus versioned Python preparation.
- **Critical cleanup:** explicitly **log out of Canvas**, not merely close its tab.
- **Checkpoint:** Learners identify what the warning says and why dropping the column matters.
- **Transition:** “Now let's encode this decision in reproducible code and write the files XGBoost actually expects.”

### 8. Getting the data into the shape XGBoost expects
**Notebook:** §8 and §8.1.
- Built-in XGBoost's CSV input contract for this exercise: **label first**, **no header**, **numeric values only**.
- Create/run `prepare.py` in remote VS Code.
- Drop `order_id`, `order_date`, `refund_amount` from features; keep `returned` only as the target.
- One-hot encode `category` and `payment_method`; obtain **18 ordered numeric feature columns**.
- Shuffle reproducibly and split 70/15/15; **8,400 train**, **1,800 validation**, **1,800 batch**.
- Write four S3 files:

  | Output key | Rows | Columns | Content / headers |
  | --- | ---: | ---: | --- |
  | `train/train.csv` | 8,400 | 19 | Label + 18 features; no header |
  | `validation/validation.csv` | 1,800 | 19 | Label + 18 features; no header |
  | `batch-input/batch.csv` | 1,800 | 18 | Features only; no header |
  | `batch-labels/labels.csv` | 1,800 | 1 | Actual label; header retained |

- Check the first line and retain feature order for next class's prediction inputs.
- **8.1 silent-failure demonstration:** Header text can be treated as an extra data row; training may not throw an obvious error. Inspect row counts.
- **Check:** The script still retains `delivery_days`; confirm its availability at checkout before claiming the features are deployment-safe.

### 9. Shutting down until next class
**Notebook:** §9.
- Close remote VS Code window and **stop** `returns-lab`. Stopping retains persistent files.
- Confirm Canvas logout.
- Delete the **six interface** endpoints; retain **S3 gateway** endpoint.
- Delete regional NAT gateway; inspect Elastic IPs for lingering allocations.
- Explain expected private default route **blackhole** after NAT deletion; it will be repaired next class.
- Keep S3 bucket, prepared objects, IAM role, VPC/subnets/SGs, Studio domain/profile and stopped space.
- **Checkpoint:** Ask learners to list which resources can still generate ongoing charges.

### 10. Class summary
**Notebook:** §10.
- Platform-engineer path: private network + authorized role + VPC-only domain + remote IDE.
- ML-engineer path: S3 exploration -> leakage discovery -> Data Wrangler confirmation -> reproducible feature preparation.
- The biggest takeaways are often **quiet failures**: missing `StartSession` permission, incomplete closed-network connectivity, and malformed CSV headers.

### 11. References and further reading
**Notebook:** §11.
- Use the notebook's official AWS links for remote Studio access, VPC-only networking, Canvas, built-in XGBoost, NAT gateways and IAM policy behavior.
- AWS pricing references are **not static facts**; verify before giving cost estimates.

### 12. What's next
**Notebook:** §12.
- Verify the space is stopped, Canvas logged out, NAT and interface endpoints deleted, and no unused Elastic IP remains.
- Confirm all **four prepared S3 objects** exist.
- Next class: restore required connectivity, train on the prepared files, get `model.tar.gz`, and demonstrate **real-time**, **serverless** and **batch** inference.

## Suggested pacing and stopping points

| Phase | Notebook sections | Approximate explanation/demo time* |
| --- | --- | --- |
| Why we're doing this + project + costs | Preface, 1–2 | 15–20 min |
| Shared data store | 3 | 10–15 min |
| Networking | 4 | 25–40 min |
| Identity, domain and remote developer environment | 5 | 30–45 min |
| Python exploration and leakage | 6 | 15–20 min |
| Canvas visual analysis | 7 | 10–20 min |
| XGBoost CSV preparation | 8 | 15–20 min |
| Cleanup + recap | 9–12 | 10–15 min |

*These are instructional estimates only; AWS provisioning, connection setup and learner delays are **not** included. For shorter sessions, split after §5 and begin the next meeting with §6.*

## Four questions to repeat throughout the lesson

1. **Where am I right now?** AWS console, CloudShell, laptop terminal, remote VS Code, or Canvas?
2. **What does this component solve?** Connectivity, authorization, a shared dataset, a development workspace, a data-quality problem or an algorithm input requirement?
3. **What is the next handoff?** Which S3 key or AWS resource is created and who consumes it?
4. **Does it keep billing after we leave?** If yes, exactly what action stops the charge?

## Scope boundary

**Completed today:** private SageMaker setup; role/domain/space; remote VS Code; S3 dataset analysis; leakage demonstration; Canvas report; four prepared data files; cleanup.

**Not completed today:** a SageMaker managed XGBoost training job, `model.tar.gz` creation, real-time/serverless deployment, batch transform and production inference. These belong to the next notebook/class.
