# Milepost API on EC2 — End-to-End Project Flow

A one-page mental map of the project in `README(4).md`. The labels below refer to the README's numbered steps.

```text
START — One Milepost API, deployed on two EC2 machines
  │
  ▼
[STEP 0 · OPTIONAL] Understand the application before deploying it
  ├── FastAPI serves two ML models:
  │     used-car price estimator (XGBoost) + loan pre-check (scikit-learn)
  ├── Docker packages the API, dependencies and model artifacts
  ├── Local test: http://localhost:8000/docs
  └── Goal: run the SAME image on two machines in different AWS AZs
  │
  ▼
[STEP 1] Pick the AWS geography — us-west-2 (Oregon)
  ├── Region = geographic AWS location
  ├── AZs = separate failure zones inside the Region
  └── Use us-west-2a and us-west-2b (choose existing AZs; do NOT create them)
  │
  ▼
[STEP 2] Create the VPC — milepost-ec2-vpc · 10.0.0.0/16
  └── One private AWS network, spanning both AZs
  │
  ▼
[STEP 3] Divide the VPC into two subnets — one in EACH AZ
  │
  ├── us-west-2a ── milepost-ec2-public-a · 10.0.1.0/24
  │
  └── us-west-2b ── milepost-ec2-public-b · 10.0.2.0/24
       └── Enable auto-assign PUBLIC IPv4 on both subnets
  │
  ▼
[STEPS 4–5] Give the subnets an internet path
  │
  ├── Internet gateway: milepost-ec2-igw
  │     └── Create it, then ATTACH it to the VPC
  │
  ├── Route table: milepost-ec2-public-rt
  │     ├── 10.0.0.0/16  → local          (inside this VPC)
  │     └── 0.0.0.0/0    → internet gateway (outside this VPC)
  │
  └── ASSOCIATE this route table with BOTH subnets
        └── Public subnet needs a route to IGW; public IP is not enough
  │
  ▼
[STEP 6] Guard the machines with a security group
  └── milepost-ec2-host-sg
        ├── INBOUND: TCP 8000 only from My IP
        ├── OUTBOUND: all traffic allowed (needed for bootstrapping)
        └── No inbound SSH port 22 (Session Manager can provide shell)
  │
  ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ TWO PREPARATIONS BEFORE THE EC2 MACHINES CAN START THE APP       │
  │                                                                 │
  │ [STEP 7] Application/image track      [STEP 8] Identity track   │
  │  ├── Build Docker image (amd64)       ├── IAM role:             │
  │  ├── Create ECR repository           │   MilepostEc2Role       │
  │  │   milepost-ec2                    ├── ECR read-only access   │
  │  ├── Tag image v1                    ├── SSM managed access    │
  │  └── Push image to ECR               └── Attach via EC2        │
  │                                           instance profile      │
  │                                                                 │
  │ Image = WHAT should run              Role = WHAT EC2 may access │
  └───────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼
[STEP 9] Launch the SAME container on two EC2 instances
  │
  ├── EC2 A: milepost-ec2-a               EC2 B: milepost-ec2-b
  │   ├── AZ us-west-2a                    ├── AZ us-west-2b
  │   ├── subnet 10.0.1.0/24               ├── subnet 10.0.2.0/24
  │   ├── public IPv4 enabled              ├── public IPv4 enabled
  │   └── t3.micro                         └── t3.micro
  │
  ├── BOTH: attach milepost-ec2-host-sg and MilepostEc2Role
  │
  └── BOTH: pass the same user_data.sh script at first boot
        ├── Read own AZ + instance ID from instance metadata (IMDSv2)
        ├── Install and start Docker
        ├── Authenticate to ECR using temporary IAM role credentials
        ├── Pull milepost-ec2:v1
        └── Start API container on port 8000; pass AZ + instance ID
  │
  ▼
[STEP 10] Verify the deployment — two public IPs, two live copies
  │
  ├── http://PUBLIC-IP-A:8000/ ──→ served_by: us-west-2a + instance A
  ├── http://PUBLIC-IP-B:8000/ ──→ served_by: us-west-2b + instance B
  │
  ├── GET /health              → confirm BOTH ML models can run
  ├── POST /predict/price      → used-car price inference
  ├── POST /predict/loan       → loan pre-check inference
  └── GET /docs                → interactive API documentation
  │
  ▼
[STEP 11] FAILURE EXPERIMENT — manually STOP EC2 A
  │
  ├── Calls to A's old public IP → FAIL
  ├── Calls to B's public IP     → still WORK
  ├── Will AWS create a replacement for A? → NO
  ├── Will clients automatically switch from A to B? → NO
  └── Restart A → same instance ID/private IP, typically new public IP;
                  Docker restarts its container
  │
  ▼
[STEP 12 · OPTIONAL] Want ONE address and healthy-instance routing?
  │                     (run in the README, on a rebuild of the same setup)
  │
  ├── NO ──→ Keep two independent public endpoints; manual switching
  │
  └── YES ─→ Add Application Load Balancer (requires ELB permission)
             ├── ALB security group: inbound HTTP 80
             ├── Target group: instances A + B, HTTP 8000
             ├── Health check: GET /health
             ├── Internet-facing ALB in both public subnets
             ├── ALB listener: HTTP 80 → target group
             ├── Change EC2 security group: allow 8000 from ALB SG,
             │   not directly from My IP
             └── Client → ONE ALB DNS name → healthy EC2 target
                   ├── If A fails, ALB routes to healthy B
                   └── ALB does NOT replace A (Auto Scaling is separate)
  │
  ▼
[STEP 14] CLEAN UP — avoid ongoing charges
  ├── Delete ALB + target group, if created
  ├── Terminate EC2 A and EC2 B
  ├── Delete VPC (with subnets, route table, IGW, security groups)
  ├── Delete ECR repository and image
  └── Delete IAM role if permitted; remove local Docker images
  │
  ▼
END — Network → container registry + permissions → two deployments
      → direct testing → failure experiment → optional load balancing
```

## Keep these three traffic paths separate

```text
1. IMAGE DELIVERY (at first boot)
   EC2 instance ── IAM role authorizes ──→ ECR ── docker pull ──→ EC2

2. USER REQUESTS (without the optional ALB)
   Browser ──→ public IP :8000 ──→ internet gateway / VPC routing
           ──→ instance security group ──→ Docker container / FastAPI

3. USER REQUESTS (only if the optional ALB is created)
   Browser ──→ ALB DNS :80 ──→ target group + /health checks
           ├──→ EC2 A :8000 (healthy)
           └──→ EC2 B :8000 (healthy)
```

**Key distinction:** A VPC defines the network, subnets place resources in particular AZs, the route table chooses a destination for outgoing traffic, the internet gateway enables internet connectivity, and security groups control which traffic is allowed. None of these components is itself a load balancer or a replacement mechanism.

**Execution status in the README:** every step was performed, including the ALB (step 12, on a rebuild of the same setup) and cleanup. There is no Step 13 deployment stage: Section 13 is troubleshooting.
