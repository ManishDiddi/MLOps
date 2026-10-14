# Milepost API on ECS Fargate, across two Availability Zones

## What we're trying to do

**Run one API as containers that AWS starts, watches and replaces for you, spread over two Availability Zones, inside a network built piece by piece.**

- **Starts from:** the Milepost API in `app/`, a FastAPI service with two models: a used-car price estimator (XGBoost) and a loan pre-check (scikit-learn).
- **Ends with:** the same Docker image running as two Fargate tasks of one ECS service:
  - one task in `us-west-2a`
  - one task in `us-west-2b`
- **No servers to manage:** no instance to launch, no Docker to install, no SSH. You describe the container once; ECS keeps two copies running.
- **Every answer says which copy served it:** the Availability Zone and the task ID.
- **The service offers:**

| Route | What it does |
|---|---|
| `GET /` | Service name and `served_by` (AZ + task ID) |
| `GET /health` | Scores a fixed test car and buyer to prove both models load; also returns `served_by` |
| `POST /predict/price` | Resale price in lakhs for one car |
| `POST /predict/price/batch` | Prices for up to 1,000 cars in one call |
| `POST /predict/loan` | Loan decision, probability, and the threshold applied |
| `GET /docs` | Interactive page for trying every route from the browser |

```mermaid
flowchart LR
    user["Browser or curl"] -->|"http://TASK-PUBLIC-IP:8000"| igw["Internet gateway"]
    subgraph region["Region us-west-2 (Oregon)"]
        subgraph vpc["VPC milepost-fargate-vpc 10.1.0.0/16"]
            igw --> a
            igw --> b
            subgraph aza["AZ us-west-2a, subnet 10.1.1.0/24"]
                a["Fargate task<br/>container milepost on 8000"]
            end
            subgraph azb["AZ us-west-2b, subnet 10.1.2.0/24"]
                b["Fargate task<br/>container milepost on 8000"]
            end
        end
        svc["ECS service milepost-fargate-service<br/>desired count 2"]
        ecr["ECR repository milepost-fargate"]
        logs["CloudWatch log group<br/>/ecs/milepost-fargate-task"]
    end
    svc -.->|"starts and replaces"| a
    svc -.->|"starts and replaces"| b
    ecr -.->|"image pull when a task starts"| a
    ecr -.->|"image pull when a task starts"| b
    a -.->|"container output"| logs
    b -.->|"container output"| logs
```

## How we're doing it

**Build each network piece in the AWS console, describe the container once in a task definition, then let an ECS service keep two copies running, one per AZ.**

| Step | The problem | What fixes it |
|---|---|---|
| VPC | You need your own private network in AWS | A VPC with the range `10.1.0.0/16` |
| Two subnets | One data centre can fail | One subnet in `us-west-2a`, one in `us-west-2b` |
| Internet gateway + route table | A new subnet cannot reach the internet, and nothing outside can reach it | `0.0.0.0/0 → internet gateway` on both subnets |
| Security group | A task accepts no inbound traffic by default | Allow port 8000 from your own IP only |
| ECR | ECS needs somewhere to pull the image from | A private repository, `milepost-fargate` |
| Execution role | ECS needs permission to pull the image and write logs on your behalf | `MilepostFargateExecutionRole` with `AmazonECSTaskExecutionRolePolicy` |
| Log group | The container's output has to land somewhere you can read it | `/ecs/milepost-fargate-task` in CloudWatch Logs |
| Cluster | Services and tasks need a home | `milepost-fargate-cluster`, Fargate only |
| Task definition | ECS needs a recipe: image, CPU and memory, port, role, logs | `milepost-fargate-task` |
| Service | Someone has to start the containers and replace any that stop | `milepost-fargate-service`: 2 tasks over both subnets |
| Experiments | What does ECS do when you scale, or when a task stops? | Scale 2 → 4 → 2; stop a task by hand and watch the replacement |
| Load balancer | Every task has its own address, and it changes when a task is replaced | One DNS name in front; ECS registers each task's IP for you |

- Everything happens in **US West (Oregon), `us-west-2`**.
- **Every step was run as shown;** the outputs quoted are real.
- **Step 15 was run on a rebuild of the same setup,** so its task IDs and addresses differ from steps 13–14.

## How to go through this folder

### What you need

| For | You need |
|---|---|
| All steps | An AWS account that can use VPC, EC2 security groups, ECR, ECS, CloudWatch Logs and IAM roles in `us-west-2` |
| Pushing the image (step 7) | AWS CLI v2, configured with `aws configure` (region `us-west-2`), and Docker Desktop |
| The load balancer (step 15) | Elastic Load Balancing permission in the same account |

### The route

1. **Optional:** run the API on your laptop (step 0).
2. Choose the Region and look at its AZs (step 1).
3. Build the network: VPC, subnets, internet gateway, route table (steps 2–5).
4. Create the security group, push the image to ECR, create the execution role and the log group (steps 6–9).
5. Create the cluster, the task definition and the service (steps 10–12).
6. Call the API on both tasks (step 13), then scale and stop tasks and watch ECS react (step 14).
7. Put a load balancer in front, attach it to the service, then stop a task again and compare (step 15).
8. Clean up (step 17).

- Commands are written for **bash**. On Windows, run them in Git Bash or WSL.

### Files

| File | Used in | What it is |
|---|---|---|
| `app/fastapi_app.py` | Steps 0 and 7 | The API: two models and the routes above; reports `served_by` from the ECS task metadata |
| `app/requirements.txt` | Steps 0 and 7 | Pinned packages. `xgboost-cpu` is the CPU-only build of XGBoost 3.2.0: same `import xgboost`, without the NVIDIA libraries the regular Linux wheel pulls in |
| `app/Dockerfile` | Steps 0 and 7 | `python:3.12-slim` + packages + app + models; runs `uvicorn` on port 8000 as a non-root user |
| `app/artifacts/` | Steps 0 and 7 | `price_model.joblib`, `loan_model.joblib`, `model_meta.json` |
| `task-definition.json` | Step 11 | The same task definition as JSON, for registering it from a terminal instead of the console |
| `screenshots/` | Every step | Console screenshots, numbered in step order |

## Words used here

| Word | Meaning |
|---|---|
| Region | A geographic area with its own copy of AWS, such as `us-west-2` (Oregon) |
| Availability Zone (AZ) | One or more data centres inside a Region, with separate power and networking. `us-west-2` has four: `us-west-2a` to `us-west-2d` |
| AZ ID | The physical zone behind an AZ name, such as `usw2-az1`. AZ names can map to different physical zones in different accounts; AZ IDs don't |
| VPC | Your private network inside a Region. It spans every AZ of that Region |
| CIDR | An address range written as `10.1.0.0/16`: the `/16` says how many leading bits are fixed |
| Subnet | A slice of the VPC's range that lives in exactly one AZ |
| Internet gateway | The VPC's door to the internet |
| Route table | Rules that say where traffic for each destination goes |
| Public subnet | A subnet whose route table sends `0.0.0.0/0` to an internet gateway |
| Security group | A firewall attached to each network interface; inbound traffic is blocked unless a rule allows it |
| ECR | Elastic Container Registry: AWS's private Docker registry |
| ECS | Elastic Container Service: you describe a container, and ECS starts it, watches it and replaces it |
| Fargate | The way of running ECS tasks without servers: AWS supplies a right-sized machine for each task, and you never see it |
| Cluster | A named group for services and tasks. A Fargate-only cluster holds no machines |
| Task definition | The recipe for a task: image, CPU, memory, port, roles and log settings. Every change makes a new revision (`:1`, `:2`, …) |
| Task | One running copy of a task definition, with its own network interface and IP addresses |
| Service | Keeps a set number of tasks running (the desired count) and replaces any task that stops |
| ENI | Elastic network interface: a virtual network card in a subnet. With Fargate, every task gets its own ENI, private IP and security group |
| Execution role | The IAM role ECS uses while starting your task: pull the image from ECR, send the container's output to CloudWatch Logs |
| Task role | The IAM role the code inside the container uses to call AWS services. Not needed here |
| Task metadata endpoint | An address inside each task, given to the container as `ECS_CONTAINER_METADATA_URI_V4`, that tells it its task ID, AZ and more |
| Log group | A named place in CloudWatch Logs that holds log streams; ECS writes one stream per container |
| Target group | The list of targets a load balancer may send requests to, plus their health check. For Fargate the targets are task IPs |
| ALB | Application Load Balancer: one HTTP entry point that spreads requests across healthy targets |
| Listener | The port and protocol a load balancer accepts (here HTTP 80), and where it forwards those requests |
| Health check | A request the load balancer sends every target on a schedule (here `GET /health` every 30 seconds); only targets that pass get traffic |
| Draining | A target on its way out of a target group: it gets no new requests while the open ones finish |

## 0. Run the API on your laptop (optional)

**The same image runs on your laptop and on Fargate; only `served_by` changes.**

```bash
cd app
docker build --platform linux/amd64 -t milepost-fargate:v1 .
docker run --rm -p 8000:8000 milepost-fargate:v1
```

- Open `http://localhost:8000/docs` to see the API. `GET /` answers with `"availability_zone": "local"` and `"task_id": "local"`, because outside ECS there is no task metadata to read.
- Stop the container with `Ctrl+C`.
- **Why `--platform linux/amd64`:** the task definition (step 11) asks for **Linux/X86_64**. An image built on an Apple Silicon Mac is arm64 unless you ask otherwise, and the task stops with `exec format error`. Docker Desktop still runs the amd64 image on a Mac, just more slowly.

## 1. Region and Availability Zones

**`us-west-2` is a Region. `us-west-2a` to `us-west-2d` are its Availability Zones. You choose an AZ for every subnet; you never create one.**

- In the console header, choose **United States (Oregon)**.
- The AZ list appears when you create a subnet (step 3):

![The subnet form lists Oregon's four AZs, each with its AZ ID](screenshots/01_subnet_az_choices.jpg)

- Each entry shows the AZ name and its AZ ID. In the account used here, `us-west-2a` is `usw2-az2` and `us-west-2b` is `usw2-az1`. In your account the pairs may differ: the names are shuffled per account, the AZ IDs are not.
- **Two AZs = two subnets.** A second subnet in the same AZ does not protect against that AZ failing.

## 2. Create the VPC

**A VPC is your private network in the Region. It spans every AZ; subnets come next.**

- **VPC → Your VPCs → Create VPC**

| Setting | Value |
|---|---|
| Resources to create | VPC only |
| Name tag | `milepost-fargate-vpc` |
| IPv4 CIDR | `10.1.0.0/16` |
| IPv6 CIDR block | No IPv6 CIDR block |
| Tenancy | Default |
| VPC encryption control | None |

![Create VPC with VPC only, name and 10.1.0.0/16](screenshots/02_create_vpc.jpg)

- `10.1.0.0/16` gives 65,536 private addresses to divide into subnets.

## 3. Create two subnets, one per AZ

**A subnet lives in exactly one AZ, so spreading over two AZs takes two subnets.**

- **VPC → Subnets → Create subnet**, choose VPC `milepost-fargate-vpc`, then use **Add new subnet** for the second one in the same form.

| Setting | Subnet 1 | Subnet 2 |
|---|---|---|
| Subnet name | `milepost-fargate-public-a` | `milepost-fargate-public-b` |
| Availability Zone | `us-west-2a` | `us-west-2b` |
| IPv4 subnet CIDR block | `10.1.1.0/24` | `10.1.2.0/24` |

![Subnet 1: us-west-2a, 10.1.1.0/24](screenshots/03_subnet_a_form.jpg)

![Subnet 2: us-west-2b, 10.1.2.0/24](screenshots/04_subnet_b_form.jpg)

![Both subnets created](screenshots/05_subnets_created.jpg)

- **Subnet arithmetic:** a `/24` holds 256 addresses. AWS keeps 5 in every subnet (network address, VPC router, DNS, one reserved, broadcast), so **251** are usable. Every Fargate task and load balancer node takes one.

![Subnet details: us-west-2a, 10.1.1.0/24, 251 available addresses](screenshots/06_subnet_a_details.jpg)

- For **each** subnet: select it → **Actions → Edit subnet settings** → tick **Enable auto-assign public IPv4 address** → **Save**.

![Enable auto-assign public IPv4 address](screenshots/07_subnet_auto_assign_ip.jpg)

- **Fargate ignores this setting.** A task gets a public IP only from the service's **Public IP** switch (step 12): a test task started in this subnet with that switch off got no public IP. The setting still matters for anything else you launch here, such as EC2 instances.

## 4. Give the subnets a way to the internet

**A subnet is "public" only when its route table sends `0.0.0.0/0` to an internet gateway. A public IP alone is not enough.**

### 4.1 Internet gateway

- **VPC → Internet gateways → Create internet gateway**, name `milepost-fargate-igw`.

![Create internet gateway](screenshots/08_create_igw.jpg)

- A new gateway is **Detached**: it does nothing until it is attached to a VPC.

![The new gateway is Detached](screenshots/09_igw_detached.jpg)

- **Actions → Attach to VPC** → `milepost-fargate-vpc` → **Attach internet gateway**.

![Attach the gateway to milepost-fargate-vpc](screenshots/10_attach_igw.jpg)

![Gateway Attached](screenshots/11_igw_attached.jpg)

### 4.2 Route table

- **VPC → Route tables → Create route table**: name `milepost-fargate-public-rt`, VPC `milepost-fargate-vpc`.

![Create route table](screenshots/12_create_route_table.jpg)

- A new route table has one route: `10.1.0.0/16 → local`, traffic between addresses inside the VPC.
- **Routes → Edit routes → Add route**: destination `0.0.0.0/0`, target **Internet Gateway** → `milepost-fargate-igw` → **Save changes**.

![0.0.0.0/0 to the internet gateway, next to the local route](screenshots/13_route_to_igw.jpg)

- **Subnet associations → Edit subnet associations** → tick both subnets → **Save associations**.

![Associate both subnets](screenshots/14_subnet_associations.jpg)

- Until you associate them, the subnets use the VPC's **main** route table, which has no internet route.

## 5. Check the network

**The resource map shows the whole chain on one screen.**

- **VPC → Your VPCs → `milepost-fargate-vpc` → Resource map**

![VPC → two subnets in us-west-2a and us-west-2b → public route table → internet gateway](screenshots/15_resource_map.jpg)

- Both subnets connect to `milepost-fargate-public-rt`, and it connects to `milepost-fargate-igw`.
- The second route table, `rtb-…`, is the VPC's main table. Nothing uses it now.

## 6. Security group for the tasks

**A security group is a firewall around each task's network interface. Nothing comes in until a rule allows it.**

- **EC2 → Security Groups → Create security group**

| Setting | Value |
|---|---|
| Security group name | `milepost-fargate-task-sg` |
| Description | `Milepost API on port 8000` |
| VPC | `milepost-fargate-vpc` (the console starts on the default VPC; change it) |
| Inbound rule | Type **Custom TCP**, port **8000**, source type **My IP** |
| Outbound rule | Leave **All traffic** to `0.0.0.0/0` (each task pulls its image from ECR and sends logs to CloudWatch) |

![Inbound 8000 from My IP](screenshots/16_security_group.jpg)

- **One group, many interfaces:** every task gets its own network interface, and each one carries this group.
- **No SSH rule:** there is no machine to log in to. You read what a container prints in the service's **Logs** tab (step 13).
- **My IP** fills in the address your browser uses right now. Home connections change addresses; when yours does, calls time out (see step 16).

## 7. Put the image in ECR

**ECR is AWS's private Docker registry; every new task pulls the image from it.**

- **ECR → Private registry → Repositories → Create repository**: name `milepost-fargate`, image tag mutability **Mutable**, encryption **AES-256**.

![Create the milepost-fargate repository](screenshots/17_ecr_create_repo.jpg)

- Build and push from your laptop:

```bash
cd app
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGISTRY=$ACCOUNT_ID.dkr.ecr.us-west-2.amazonaws.com

aws ecr get-login-password --region us-west-2 |
  docker login --username AWS --password-stdin $REGISTRY

docker build --platform linux/amd64 -t milepost-fargate:v1 .
docker tag milepost-fargate:v1 $REGISTRY/milepost-fargate:v1
docker push $REGISTRY/milepost-fargate:v1
```

- Expect `Login Succeeded`, then `v1: digest: sha256:… size: …`. The image is about 165 MB; the push took 35 seconds here.

![The repository holds v1 (165 MB) and two untagged entries](screenshots/18_ecr_image_pushed.jpg)

- The two **untagged** entries next to `v1` are the image index and build attestation Docker pushes along with the image; leave them.
- **Keep the image URI handy** for step 11: `<account-id>.dkr.ecr.us-west-2.amazonaws.com/milepost-fargate:v1`. **Copy URI** in the repository gives it to you.

## 8. Execution role

**Before your code runs, ECS itself has to pull the image and connect the logs. The execution role is the permission it does that with.**

- **IAM → Roles → Create role**
  1. **Trusted entity type:** AWS service. **Service or use case:** Elastic Container Service. **Use case:** **Task Execution Role for Elastic Container Service** → Next.

![Use case: Task Execution Role for Elastic Container Service](screenshots/19_iam_trusted_entity.jpg)

  2. **Permissions:** this use case attaches `AmazonECSTaskExecutionRolePolicy` for you. Expand it to see what it allows: pull from ECR, then create log *streams* and write log events. It cannot create log *groups*, which is why step 9 exists → Next.

![AmazonECSTaskExecutionRolePolicy: four ECR actions, logs:CreateLogStream and logs:PutLogEvents](screenshots/20_iam_execution_policy.jpg)

  3. **Role name:** `MilepostFargateExecutionRole` → **Create role**.

![Role name, and the trust policy for ecs-tasks.amazonaws.com](screenshots/21_iam_role_name_trust.jpg)

- The review screen shows both halves of a role:
  - **Trust policy:** who may use it, `ecs-tasks.amazonaws.com`;
  - **Permissions:** what it may do.
- **Execution role and task role are different things:**

| Role | Used by | For | Here |
|---|---|---|---|
| Execution role | ECS, while it starts and runs your task | Pulling the image from ECR, sending the container's output to CloudWatch Logs | `MilepostFargateExecutionRole` |
| Task role | Your code inside the container | Calling AWS services from the app, such as S3 or DynamoDB | None: Milepost calls no AWS service |

- The use case list also has **Elastic Container Service Task**: that one is for building a task role.

## 9. Create the log group

**The container's output goes to a CloudWatch log group. Create it before the first task starts.**

- **CloudWatch → Logs → Log Management → Create log group**

| Setting | Value |
|---|---|
| Log group name | `/ecs/milepost-fargate-task` |
| Retention setting | 1 week (7 days) |
| Log class | Standard |

![Create log group /ecs/milepost-fargate-task, 1 week retention](screenshots/22_create_log_group.jpg)

- **Why by hand:** the task definition form (step 11) sends logs to `/ecs/<task definition name>` and asks ECS to create that group if it's missing. Creating a group needs `logs:CreateLogGroup`, which the execution role doesn't have (screenshot 20). A test task pointed at a missing group never started:

```text
ResourceInitializationError: failed to validate logger args: create stream has been retried 1 times:
failed to create Cloudwatch log group: ... AccessDeniedException: User: arn:aws:sts::<account-id>:assumed-role/MilepostFargateExecutionRole/...
is not authorized to perform: logs:CreateLogGroup ...
```

- **1 week retention:** older log lines are deleted for you, so the group never grows without limit.

## 10. Create the cluster

**A cluster is the home for services and tasks. With Fargate it holds no machines.**

- **ECS → Clusters → Create cluster**: cluster name `milepost-fargate-cluster`, infrastructure **Fargate only** → **Create**.

![Create cluster: Fargate only](screenshots/23_create_cluster.jpg)

- The new cluster is only a name so far: no services, no tasks, and no machines, now or later.

![Cluster created: 0 services, no tasks, 0 EC2](screenshots/24_cluster_created.jpg)

## 11. Create the task definition

**The task definition is the recipe ECS follows for every copy: which image, how much CPU and memory, which port, which role, where the logs go.**

- **ECS → Task definitions → Create new task definition**

| Setting | Value |
|---|---|
| Task definition family | `milepost-fargate-task` |
| Launch type | AWS Fargate |
| Operating system/Architecture | Linux/X86_64 |
| Network mode | `awsvpc` (fixed for Fargate) |
| CPU / Memory | .25 vCPU / .5 GB |
| Task role | – (none) |
| Task execution role | `MilepostFargateExecutionRole` (the form starts on **Create default role**; change it) |
| Container name | `milepost`, essential container **Yes** |
| Image URI | `<account-id>.dkr.ecr.us-west-2.amazonaws.com/milepost-fargate:v1` |
| Port mappings | Container port **8000**, TCP, app protocol HTTP |
| Log collection | On: Amazon CloudWatch. The form fills in `awslogs-group` `/ecs/milepost-fargate-task`; leave the rest as it is |

![Fargate, Linux/X86_64, .25 vCPU, .5 GB, the execution role](screenshots/25_taskdef_infrastructure.jpg)

![Container milepost, the ECR image URI, port 8000](screenshots/26_taskdef_container.jpg)

![Log collection to /ecs/milepost-fargate-task, the group from step 9](screenshots/27_taskdef_logging.jpg)

- **Create.** The result is revision 1, `milepost-fargate-task:1`. Any later change creates `:2`, `:3`, …; old revisions stay until you deregister them.

![milepost-fargate-task:1: 256 CPU units, 512 MiB, the execution role, no task role](screenshots/28_taskdef_created.jpg)

- **Why 0.25 vCPU and 0.5 GB:** it is the smallest Fargate size. The API uses about 220 MB of memory with both models loaded, so 0.5 GB leaves room.
- **The same thing from a terminal:** `task-definition.json` holds these settings with `ACCOUNT_ID` in place of your account number.

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
sed "s/ACCOUNT_ID/$ACCOUNT_ID/g" task-definition.json > task-definition.mine.json
aws ecs register-task-definition --cli-input-json file://task-definition.mine.json
```

## 12. Create the service

**The service is the part that keeps two tasks running: it starts them, spreads them over the subnets you give it, and replaces any that stop.**

- **ECS → Clusters → `milepost-fargate-cluster` → Services → Create**

| Section | Setting | Value |
|---|---|---|
| Service details | Task definition family / revision | `milepost-fargate-task` / latest (1) |
| Service details | Service name | `milepost-fargate-service` |
| Environment | Compute options | **Launch type** → Fargate, platform version LATEST |
| Deployment configuration | Scheduling strategy | Replica |
| Deployment configuration | Desired tasks | **2** |
| Deployment configuration | Availability Zone re-balancing | On (the default) |
| Networking | VPC | `milepost-fargate-vpc` (the form starts on the default VPC; change it) |
| Networking | Subnets | Both `milepost-fargate-public-*` subnets (selected for you once the VPC is chosen) |
| Networking | Security group | Use an existing security group → `milepost-fargate-task-sg` only (remove `default`) |
| Networking | Public IP | **Turned on** |
| Load balancing | | Leave off for now (step 15) |

![Service details and the Fargate launch type](screenshots/29_service_details.jpg)

![Replica, 2 desired tasks, AZ re-balancing on](screenshots/30_service_deployment.jpg)

![Our VPC, both subnets, the task security group, public IP on](screenshots/31_service_networking.jpg)

- **Why Public IP must be on:** each task pulls its image from ECR over the internet. With no public IP, and no NAT gateway in this VPC, it can't. A test task with the switch off sat in PENDING for 5 minutes, then stopped:

```text
ResourceInitializationError: unable to pull secrets or registry auth: The task cannot pull registry auth
from Amazon ECR: There is a connection issue between the task and Amazon ECR. Check your task network
configuration. ... dial tcp ...:443: i/o timeout
```

- **Create.** The console builds the service through a CloudFormation stack named `ECS-Console-V2-Service-milepost-fargate-service-…` and shows *Deployment in progress*.
- **What happened:** both tasks were running about 70 seconds after **Create**, one in each AZ. ECS spreads a service's tasks across the AZs of the subnets you give it.

## 13. Call the API on both tasks

**The same request, sent to each task's public IP, shows which AZ and which task answered.**

- **Service → Tasks.** The gear icon chooses the columns; **Private IP**, **Public IP** and **Availability zone** are the useful ones here.

![Two running tasks: one in us-west-2b, one in us-west-2a, each with its own private and public IP](screenshots/32_service_tasks_two_azs.jpg)

```bash
curl http://<public-ip-of-task-1>:8000/
curl http://<public-ip-of-task-2>:8000/
```

```json
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2a","task_id":"a0abc792e1834dc3ada94b77d6f2a9e4"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2b","task_id":"915fe13fb4c44e66b601ea2e9f5ce97b"}}
```

![The task in us-west-2a answers](screenshots/33_app_task_a.png)

![The task in us-west-2b answers](screenshots/34_app_task_b.png)

- **How the app knows where it runs:**
  1. ECS puts an address into every container's environment: `ECS_CONTAINER_METADATA_URI_V4`.
  2. When the app starts, it asks `GET $ECS_CONTAINER_METADATA_URI_V4/task`.
  3. The answer is JSON with `AvailabilityZone` and `TaskARN`; the task ID is the last part of the ARN.
  4. On your laptop the variable doesn't exist, so the app reports `local`.
- **In the browser:** `http://<public-ip>:8000/docs` lists every route.

![The /docs page](screenshots/35_app_docs.png)

- **Predict a price:** open **POST /predict/price → Try it out**, paste the car below, then **Execute**.

![POST /predict/price executed: 200, price_lakhs 5.31](screenshots/36_app_predict_price.png)

- **The same calls from a terminal:**

```bash
curl -X POST http://<public-ip>:8000/predict/price \
  -H 'Content-Type: application/json' \
  -d '{"year": 2018, "seller_type": "Dealer", "km_driven": 45000, "fuel_type": "Petrol",
       "transmission_type": "Manual", "mileage": 18.5, "engine": 1200, "max_power": 85.0, "seats": 5}'
# {"price_lakhs":5.31,"model_version":"milepost-2026-09-23"}

curl -X POST http://<public-ip>:8000/predict/loan \
  -H 'Content-Type: application/json' \
  -d '{"Gender": "Male", "Married": "No", "ApplicantIncome": 5000, "LoanAmount": 128,
       "Credit_History": "Cleared Debts"}'
# {"loan_approval_status":"Loan Rejected","probability":0.7448,"threshold_applied":0.8,"model_version":"milepost-2026-09-23"}
```

- A body with missing fields gets **422** before any model code runs.
- Some browsers show a "not secure" warning page for `http://` addresses. That's expected: this setup has no HTTPS. Continue past it, or use `curl`.
- **What the containers printed:** the service's **Logs** tab reads the log group from step 9. Every request appears with the task that served it, including the 422.

![Logs tab: uvicorn's request lines from both tasks](screenshots/37_service_logs.jpg)

## 14. Experiments: scale, and stop a task

**A service holds the number of tasks you ask for. Change the number, or take a task away, and ECS fixes the difference.**

### 14.1 Scale from 2 to 4

- **Service → Update service** → **Desired tasks** `4` → **Update**.

![Update service: desired tasks 4](screenshots/38_update_desired_4.jpg)

- **What happened:** two new tasks were running about 35 seconds later, one in each AZ, so each AZ held two.

![Four running tasks: two in us-west-2a, two in us-west-2b](screenshots/39_four_tasks_two_azs.jpg)

### 14.2 Stop one task by hand

- **Before you click, predict:**
  - What happens to requests sent to that task's address?
  - Does ECS start a new task, and in which AZ?
  - Does the new task keep the old address?
- **Tasks** → tick task `a0abc792…` (in `us-west-2a`) → **Stop → Stop selected → Stop**.

![Stop task: the console warns that service tasks are normally stopped by updating the service](screenshots/40_stop_task.jpg)

- **What happened:**

| Check | Result |
|---|---|
| `curl http://<old-ip-of-a0abc792>:8000/` | No answer: the connection was refused |
| Service events | About 20 seconds later: `has started 1 tasks: (task a8a1e7c17a6844ef867bf8a720de3628)` |
| The new task | `us-west-2a`, the same AZ, so the spread stays two and two |
| Its addresses | New private IP `10.1.1.146`, new public IP `100.23.103.193`, new task ID |
| The stopped task | **Stopped**, reason `Task stopped by user` |

![The stopped task, and its replacement in the same AZ with new IPs](screenshots/41_task_replaced.jpg)

![Service events: the replacement started, then a steady state](screenshots/42_service_events.jpg)

- `curl` to the replacement answered at once with `"task_id":"a8a1e7c17a6844ef867bf8a720de3628"` and `us-west-2a`.

### 14.3 Scale back to 2

- **Update service** → **Desired tasks** `2` → **Update**.
- **What happened:** ECS stopped one task in each AZ (`has stopped 2 running tasks`), so one task is left in `us-west-2a` and one in `us-west-2b`.

### 14.4 What this shows

- **A stopped task is replaced, without you doing anything.** Nothing replaces a stopped EC2 instance unless you build that; an ECS service does it by itself.
- **The replacement is a new task:** new ID, new private IP, new public IP. Anyone calling the old address now gets nothing.
- **ECS keeps the AZ spread** when it adds, replaces and removes tasks.
- **So clients need one address that doesn't change:** that is the load balancer's job (step 15).

## 15. Put a load balancer in front

**An Application Load Balancer gives one DNS name and sends each request to a healthy task. ECS adds every new task's IP to the load balancer's target group, and removes stopped ones.**

```mermaid
flowchart LR
    user["Browser or curl"] -->|"http://ALB-DNS-NAME"| alb["ALB milepost-fargate-alb<br/>a node in each AZ"]
    alb --> tg["Target group milepost-fargate-tg<br/>target type IP, health check /health"]
    tg -->|"HTTP 8000"| a["Task in us-west-2a"]
    tg -->|"HTTP 8000"| b["Task in us-west-2b"]
    svc["ECS service"] -.->|"registers new task IPs, removes stopped ones"| tg
```

### 15.1 Security group for the load balancer

- **EC2 → Security Groups → Create security group**

| Setting | Value |
|---|---|
| Security group name | `milepost-fargate-alb-sg` |
| Description | `Milepost load balancer on port 80` |
| VPC | `milepost-fargate-vpc` (the form starts on the default VPC; change it) |
| Inbound rule | Type **HTTP** (port 80), source type **Anywhere-IPv4** |
| Outbound rule | Leave **All traffic** (the load balancer forwards to the tasks on port 8000) |

![HTTP 80 from anywhere, in milepost-fargate-vpc](screenshots/43_alb_security_group.jpg)

- This is the only group open to the whole internet. The tasks' group gets a rule pointing at it in step 15.4.

### 15.2 Target group

- **EC2 → Target groups → Create target group**

| Setting | Value |
|---|---|
| Target type | **IP addresses** |
| Target group name | `milepost-fargate-tg` |
| Protocol / port | HTTP / 8000 |
| IP address type | IPv4 |
| VPC | `milepost-fargate-vpc` (the form starts on the default VPC; change it) |
| Protocol version | HTTP1 |
| Health check path | `/health` |

![Target type IP addresses, milepost-fargate-tg, HTTP 8000](screenshots/44_tg_ip_type.jpg)

![VPC and health check path /health](screenshots/45_tg_vpc_health.jpg)

- Leave **Target optimizer** off and the advanced health check settings at their defaults: a check every 30 seconds, **Healthy** after 5 passes in a row, **Unhealthy** after 2 failures.
- **Next** → register nothing → **Next** → **Create target group**. ECS registers each task's private IP itself.
- **Why IP, not Instances:** a Fargate task runs on no EC2 instance you can pick. It has its own network interface and IP, and that IP is the target.
- `/health` makes the service score a test car and buyer. A task whose models fail to load gets taken out, not just one whose port is closed.

### 15.3 Application Load Balancer

- **EC2 → Load balancers → Create load balancer → Application Load Balancer**

| Setting | Value |
|---|---|
| Load balancer name | `milepost-fargate-alb` |
| Scheme | Internet-facing |
| Load balancer IP address type | IPv4 |
| VPC | `milepost-fargate-vpc` |
| Availability Zones and subnets | `us-west-2a` → `milepost-fargate-public-a`, `us-west-2b` → `milepost-fargate-public-b` |
| Security groups | `milepost-fargate-alb-sg` only (remove `default`) |
| Listener | HTTP 80 → Forward to target groups → `milepost-fargate-tg` |

![Name, internet-facing, IPv4](screenshots/46_alb_basic.jpg)

![Two AZs, one public subnet each, each showing Route table: IGW](screenshots/47_alb_two_azs.jpg)

![ALB security group and the HTTP 80 listener forwarding to milepost-fargate-tg](screenshots/48_alb_sg_listener.jpg)

- **The console requires at least two AZs:** the load balancer places a node in each one, which is why the network has two subnets in two AZs.
- It also checks that each subnet's route table has an internet gateway route (`Route table: IGW ✓`).
- **Create load balancer.** The state goes from **Provisioning** to **Active** in a few minutes.
- Copy the **DNS name** from the details page. It is the one address clients use from now on.

![Active, a subnet in each AZ, the DNS name, and the listener forwarding to the target group](screenshots/49_alb_active.jpg)

### 15.4 Let the load balancer reach the tasks

**Do this before attaching the load balancer to the service.**

- **EC2 → Security Groups → `milepost-fargate-task-sg` → Edit inbound rules**
  1. **Delete** the port 8000 rule from My IP.
  2. **Add rule**: type **Custom TCP**, port **8000**, source **Custom** → type `sg-` and pick `milepost-fargate-alb-sg`, description `From the load balancer only`.
  3. **Preview changes** → **Confirm**.

![Preview: revoke the My IP rule, add port 8000 from the load balancer's group](screenshots/50_task_sg_from_alb.jpg)

- **Why first:** health checks and forwarded requests come from the load balancer's own addresses inside the VPC. With only the My IP rule they time out, the targets turn **Unhealthy**, and ECS replaces tasks that fail the load balancer's health check, so the deployment in step 15.5 would keep stopping its new tasks.
- **Delete and add, don't edit:** switching the existing rule's source to a security group fails with `You may not specify a referenced group id for an existing IPv4 CIDR rule.`
- The new rule shows the group by ID; `sg-0134…` here is `milepost-fargate-alb-sg`.
- From now on, the only way in is through the load balancer.
- **Leave Public IP on:** the tasks still need it to pull their image from ECR. The security group, not the missing address, is what keeps outsiders away.

### 15.5 Attach the load balancer to the service

- **ECS → `milepost-fargate-service` → Update service → Load balancing → Use load balancing → Add load balancer**

| Setting | Value |
|---|---|
| Load balancer type | Application Load Balancer |
| Container | `milepost 8000:8000` |
| Load balancer | `milepost-fargate-alb` |
| Listener | HTTP:80 |
| Target group | `milepost-fargate-tg` |

- The target group list shows why step 15.2 chose IP addresses: a target group of type Instances is greyed out with `Target type is instance but must be ip`.

![The target group list: milepost-fargate-tg, and an Instances-type group greyed out](screenshots/51_service_tg_must_be_ip.jpg)

![The service's load balancing section: type, container, load balancer, listener, target group](screenshots/52_service_add_load_balancer.jpg)

- **Update.** ECS starts a new deployment.
- **What happened:**
  - ECS started two new tasks, one per AZ, and registered each one's private IP in `milepost-fargate-tg`.
  - Both targets were **Healthy** about 1.5 minutes after **Update**.
  - Then ECS stopped the two old tasks, which had never been registered.
  - The deployment showed **Completed** about 4 minutes after **Update**.

![Both task IPs registered by ECS and Healthy, one in each AZ](screenshots/53_tg_targets_healthy.jpg)

- The target group must already be the listener's target (step 15.3); ECS refuses a target group that no load balancer uses.
- You can also choose the load balancer when you create a service, in the same **Load balancing** section.

### 15.6 Test it

```bash
for i in $(seq 1 10); do curl -s http://<alb-dns-name>/; echo; done
```

```json
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2a","task_id":"b7482780dd82424eb7a409db3ee286ac"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2b","task_id":"e482367be6db433f9435ac4af5a9ea6f"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2b","task_id":"e482367be6db433f9435ac4af5a9ea6f"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2b","task_id":"e482367be6db433f9435ac4af5a9ea6f"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2a","task_id":"b7482780dd82424eb7a409db3ee286ac"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2b","task_id":"e482367be6db433f9435ac4af5a9ea6f"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2a","task_id":"b7482780dd82424eb7a409db3ee286ac"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2a","task_id":"b7482780dd82424eb7a409db3ee286ac"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2b","task_id":"e482367be6db433f9435ac4af5a9ea6f"}}
{"service":"Milepost API","docs":"/docs","served_by":{"availability_zone":"us-west-2a","task_id":"b7482780dd82424eb7a409db3ee286ac"}}
```

- **What happened:** one address, both tasks: 5 answers from `us-west-2a`, 5 from `us-west-2b`, in no fixed order.
- **In the browser:** `http://<alb-dns-name>/` (and `/docs`) work the same way. Reload a few times to see `served_by` change.

![Through the load balancer: answered by the task in us-west-2a](screenshots/54_alb_answers_a.png)

![The same address: answered by the task in us-west-2b](screenshots/55_alb_answers_b.png)

### 15.7 Experiment: stop a task again

- **Before you click, predict:** compared with step 14.2, what does a client of the DNS name see?
- In a terminal, send one request per second and print each status code (`000` means no answer within 5 seconds):

```bash
while true; do curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://<alb-dns-name>/; sleep 1; done
```

- Then stop the task in `us-west-2a` (**Tasks → tick it → Stop → Stop selected**, as in step 14.2).
- **What happened:**

| Time after Stop | What happened |
|---|---|
| 4 seconds | ECS started a replacement task |
| 13 seconds | ECS deregistered the old task's IP: **Draining**. The old task kept running, in **Deactivating** |
| 32 seconds | The replacement's IP, `10.1.1.20`, registered: **Initial** |
| About 1 minute | The replacement **Healthy**, in `us-west-2a` like the task it replaced |
| About 5 minutes | Draining ended, then the old task stopped |
| The whole time | 196 requests, one per second: every one answered `200` |

![The old task Draining while its replacement is Initial, the other task Healthy](screenshots/56_tg_draining.jpg)

![Service events: started, deregistered, began draining, registered, steady state](screenshots/57_service_events.jpg)

- **Why 5 minutes of draining:** the target group's deregistration delay is 300 seconds by default. That's how long the load balancer gives open requests to finish before the task is stopped.
- **What this shows:**
  - In step 14.2 the stopped task's address simply went dead. Here clients kept one address, and no request failed.
  - ECS deregisters a task before stopping it, so the load balancer stops sending it requests first.
  - **Together:** the load balancer gives the one stable address; the service replaces failed tasks. Each covers what the other can't.

## 16. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `curl` to port 8000 times out, but worked earlier | Your public IP changed; the **My IP** rule still holds the old one | `curl https://checkip.amazonaws.com` shows your address. Edit the inbound rule → source type **My IP** again → **Save rules** |
| Task stops with `ResourceInitializationError: failed to validate logger args … not authorized to perform: logs:CreateLogGroup` | The log group named in the task definition doesn't exist | Create `/ecs/milepost-fargate-task` (step 9), then **Update service → Force new deployment** |
| Task stays PENDING for minutes, then stops with `ResourceInitializationError: unable to pull secrets or registry auth … i/o timeout` | The task has no route to ECR: **Public IP** is off, or the subnet's route table has no internet gateway route | **Update service → Networking → Public IP** on, tick **Force new deployment**, Update. Check the route table (step 4.2) |
| Task stops with `CannotPullContainerError` … `not found` | The image URI or tag in the task definition is wrong, or points at another Region | Copy the URI from ECR (step 7), create a new task definition revision with it, then **Update service** to that revision |
| The **Logs** tab shows `exec format error` | The image was built for arm64 | Rebuild with `--platform linux/amd64`, push again, then **Update service → Force new deployment** |
| Service stays below its desired count; its events mention a vCPU limit | The account's Fargate vCPU quota is used up | Lower the desired count, or ask for more in **Service Quotas** |
| `docker build` stops at `pip install` with `Could not find a version… (from versions: none)` | pip timed out reaching PyPI from inside Docker | Run the build again; on a slow connection add `--timeout 100` to the `pip install` line |
| Browser shows a warning page for `http://IP:8000` | Plain HTTP, no certificate | Continue past the warning, or use `curl` |
| The service's **Target group** list greys out a group: `Target type is instance but must be ip` | That target group was made with target type **Instances** | Create one with **IP addresses** (step 15.2) |
| Targets **Unhealthy**, **Request timed out**, and the service keeps replacing tasks | The tasks' security group doesn't let the load balancer in | Allow port 8000 from `milepost-fargate-alb-sg` (step 15.4) |
| `You may not specify a referenced group id for an existing IPv4 CIDR rule.` | An IP-address rule can't be switched to a security group source | Delete the rule and add a new one (step 15.4) |
| A stopped task stays in **Deactivating** for about 5 minutes | Its target is draining: the target group's deregistration delay is 300 seconds | Nothing to fix; requests already go to the other tasks |
| The target group page still shows an old health status | The page doesn't refresh by itself | Its refresh button, or reload the page |

## 17. Clean up

**Running tasks bill by the second, each with a public IP; delete everything in this order.**

1. **Load balancer:**
   - **Load balancers → tick `milepost-fargate-alb` → Actions → Delete load balancer** → type `confirm` → **Delete**. Its listener goes with it; the target group stays.

![Delete load balancer: type confirm](screenshots/58_delete_alb.jpg)

   - **Target groups → tick `milepost-fargate-tg` → Actions → Delete → Delete.**

![Delete the target group](screenshots/59_delete_tg.jpg)

   - **Why before the service:** with the target group gone, there is nothing to drain. The service's tasks stop at once instead of draining for 5 minutes each (step 15.7); the service was gone about 2 minutes after the delete.

2. **Service:** **ECS → `milepost-fargate-cluster` → Services → `milepost-fargate-service` → Delete service** → tick **Force delete** → type `delete`.
   - **Force delete** scales the service to 0 for you; without it, you set desired tasks to 0 first.
   - Its tasks stop with it, and their network interfaces were gone about a minute later.
   - The dialog says it also deletes the CloudFormation stack the console made in step 12. It did.

![Delete service: force delete, and the CloudFormation stack goes too](screenshots/60_delete_service.jpg)

3. **Cluster:** **Clusters → `milepost-fargate-cluster` → Actions → Delete cluster** → type `delete milepost-fargate-cluster`.

![Delete cluster: type the phrase to confirm](screenshots/61_delete_cluster.jpg)

4. **Task definition:**
   - **Task definitions → `milepost-fargate-task` → tick revision 1 → Actions → Deregister.**
   - Then set the filter to **Inactive** → tick it → **Actions → Delete** → type `delete`.

![Deregister: the revision becomes INACTIVE](screenshots/62_deregister_task_definition.jpg)

![Delete the inactive revision](screenshots/63_delete_task_definition.jpg)

5. **Log group:** **CloudWatch → Logs → Log Management → tick `/ecs/milepost-fargate-task` → Actions → Delete log group(s) → Delete**.

![Delete the log group](screenshots/64_delete_log_group.jpg)

6. **ECR:** **Repositories → `milepost-fargate` → Delete** → type `delete`. This deletes the images inside it too.

![Delete the milepost-fargate repository](screenshots/65_delete_ecr_repo.jpg)

7. **VPC:** **VPC → Your VPCs → `milepost-fargate-vpc` → Actions → Delete VPC** → type `delete`.
   - The dialog lists what goes with it: the internet gateway, the route table, both security groups and both subnets.
   - The task security group shows `–` as its name. That column shows the *Name tag*, which the security group form doesn't set.
   - If it refuses because of network interfaces, wait a minute: stopped tasks release theirs shortly after.

![Delete VPC lists the 6 resources deleted with it](screenshots/66_delete_vpc.jpg)

![The VPC and its 6 resources deleted; only the default VPC is left](screenshots/67_vpc_deleted.jpg)

8. **IAM:** **Roles → `MilepostFargateExecutionRole` → Delete**.
   - Some managed accounts deny role deletion. The account used here refused both detaching the policy and deleting the role (`explicit deny`).
   - Then the role stays, unused: only ECS tasks can take it on, and none exist.
9. **Laptop:**
   - `docker rmi milepost-fargate:v1 $REGISTRY/milepost-fargate:v1`
   - `docker logout $REGISTRY`

- **Check that nothing is left.** Empty output means clean:

```bash
aws elbv2 describe-load-balancers --query 'LoadBalancers[].LoadBalancerName' --output text
aws elbv2 describe-target-groups --query 'TargetGroups[].TargetGroupName' --output text
aws ecs list-clusters --query 'clusterArns' --output text
aws ecs list-task-definitions --family-prefix milepost-fargate-task --query 'taskDefinitionArns' --output text
aws logs describe-log-groups --log-group-name-prefix /ecs/milepost-fargate --query 'logGroups[].logGroupName' --output text
aws ecr describe-repositories --query 'repositories[].repositoryName' --output text
aws ec2 describe-vpcs --filters Name=is-default,Values=false --query 'Vpcs[].VpcId' --output text
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query "StackSummaries[?starts_with(StackName, 'ECS-Console')].StackName" --output text
```

## 18. Reference

### Names used

| Resource | Name |
|---|---|
| VPC | `milepost-fargate-vpc`, `10.1.0.0/16` |
| Subnets | `milepost-fargate-public-a` (`us-west-2a`, `10.1.1.0/24`), `milepost-fargate-public-b` (`us-west-2b`, `10.1.2.0/24`) |
| Internet gateway | `milepost-fargate-igw` |
| Route table | `milepost-fargate-public-rt` |
| Security groups | `milepost-fargate-task-sg` (tasks), `milepost-fargate-alb-sg` (load balancer) |
| ECR repository | `milepost-fargate`, tag `v1` |
| Execution role | `MilepostFargateExecutionRole` |
| Log group | `/ecs/milepost-fargate-task` |
| Cluster / task definition / service | `milepost-fargate-cluster` / `milepost-fargate-task` / `milepost-fargate-service` |
| Container | `milepost`, port 8000 |
| Target group / load balancer | `milepost-fargate-tg` / `milepost-fargate-alb` |

### Costs (us-west-2 on-demand list prices)

| Item | Price |
|---|---|
| Fargate task, 0.25 vCPU + 0.5 GB | $0.04048 per vCPU-hour + $0.004445 per GB-hour: about $0.0123 per hour each |
| Public IPv4 address | $0.005 per hour each (one per task) |
| ECR storage | $0.10 per GB-month (the 165 MB image: about $0.02 per month) |
| CloudWatch Logs | $0.50 per GB ingested; these request lines come to a few kilobytes |
| Load balancer | $0.0225 per hour plus usage (LCU), and $0.005 per hour for each of its public IPv4 addresses (one per AZ here) |

- Two tasks running cost about **$0.035 per hour, roughly $0.83 per day**. The load balancer adds about **$0.035 per hour**. Cleaning up ends all of it.
