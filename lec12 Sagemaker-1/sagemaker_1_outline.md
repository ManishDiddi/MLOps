```
START — We need a secure ML development environment on AWS
  │
  │  Our application will:
  │    • Download training datasets from S3
  │    • Install Python packages from the internet
  │    • Communicate with SageMaker APIs
  │    • Run JupyterLab / VS Code
  │
  ▼
[N0] WHAT NETWORK SHOULD HOST OUR ML ENVIRONMENT?
  │
  ├── VPC: returns-ml-vpc
  │     CIDR: 10.0.0.0/16
  │
  ├── Availability Zone A
  │     └── Private Subnet A
  │
  └── Availability Zone B
        └── Private Subnet B
  │
  ▼
[N1] WHY ARE WE USING PRIVATE SUBNETS?
  │
  ├── We do not need internet users to directly reach
  │   our SageMaker application machines.
  │
  ├── Instances do not require public IP addresses.
  │
  └── BUT — the machines still need outbound connectivity!
        │
        ├── Download packages from PyPI
        ├── Access external APIs
        ├── Download datasets from S3
        └── Communicate with other AWS services
        │
        ▼
[N2] HOW CAN PRIVATE RESOURCES ACCESS THE INTERNET?
  │
  ├── Internet Gateway alone?
  │     └── NOT sufficient for private-IP-only instances.
  │
  └── SOLUTION: NAT GATEWAY
        │
        ├── Allows private resources to INITIATE
        │   outbound internet connections.
        │
        ├── Return traffic is allowed for those connections.
        │
        ├── Does not independently permit unsolicited
        │   inbound internet connections.
        │
        ├── This notebook: REGIONAL NAT GATEWAY
        │     ├── Supports both selected AZs
        │     └── No customer-created public subnet needed
        │
        └── Private route table:
              0.0.0.0/0 → Regional NAT Gateway
        │
        ▼
     EXAMPLE: pip install pandas
        │
        SageMaker application
          → Private subnet
          → Route table
          → NAT Gateway
          → Internet egress / Internet Gateway
          → Public PyPI servers
        │
        ▼
[N3] PROBLEM — DO WE NEED NAT FOR ALL AWS SERVICES?
  │
  │  Suppose SageMaker downloads 500 GB from Amazon S3.
  │  If routed through NAT, data processing costs apply.
  │
  │  Can we reach supported AWS services privately
  │  without sending that traffic through NAT?
  │
  └── SOLUTION: VPC ENDPOINTS
        │
        ├── TYPE A: GATEWAY ENDPOINT
        │     │
        │     ├── Supported services: S3 and DynamoDB
        │     ├── No additional endpoint charges
        │     ├── Works through ROUTE TABLE entries
        │     └── Does not create an ENI in your subnet
        │
        │     EXAMPLE: S3 Gateway Endpoint
        │
        │       SageMaker application
        │         → Private subnet
        │         → Route table
        │         → S3 Gateway Endpoint
        │         → Amazon S3
        │
        │       No NAT Gateway required for this request!
        │
        │
        └── TYPE B: INTERFACE ENDPOINT
              │
              ├── Available for many AWS services
              ├── Powered by AWS PrivateLink
              ├── Creates private ENIs in selected subnets
              ├── These ENIs have PRIVATE IP addresses
              ├── Has hourly and data-processing charges
              │
              └── Examples used in our project:
                    │
                    ├── sagemaker.api
                    │     → SageMaker control-plane API
                    │
                    ├── sagemaker.runtime
                    │     → Invoke deployed ML endpoints
                    │
                    ├── sts
                    │     → Security Token Service
                    │
                    ├── logs
                    │     → CloudWatch Logs
                    │
                    ├── ssm
                    │     → Systems Manager
                    │
                    └── ssmmessages
                          → Session Manager communication
        │
        ▼
[N4] HOW DOES AN INTERFACE ENDPOINT WORK?
  │
  │  Example:
  │  SageMaker application calls the SageMaker API.
  │
  ├── Without Interface Endpoint:
  │
  │     Application
  │       → NAT Gateway
  │       → Public SageMaker API endpoint
  │
  └── With Interface Endpoint + PRIVATE DNS:
        │
        │  Application calls the SAME API hostname:
        │
        │  api.sagemaker.us-east-1.amazonaws.com
        │
        ▼
      DNS resolves that hostname to a private
      endpoint IP inside the VPC
        │
        ▼
      Traffic follows local VPC routing
        │
        ▼
      Interface Endpoint ENI
        │
        ▼
      AWS SageMaker API through PrivateLink

      KEY IDEA:
      Application code does not need a new API URL
      when private DNS is configured correctly.
  │
  ▼
[N5] WHAT DO OUR PRIVATE ROUTE TABLES LOOK LIKE?
  │
  │  Destination              Target
  │  -----------------------------------------------
  │  10.0.0.0/16              local
  │  S3 managed prefix list   S3 Gateway Endpoint
  │  0.0.0.0/0                Regional NAT Gateway
  │
  ├── Destination inside VPC?
  │     └── LOCAL route
  │
  ├── Destination matches the S3 prefix list?
  │     └── S3 Gateway Endpoint
  │
  ├── Interface Endpoint hostname resolved to private IP?
  │     └── LOCAL route to endpoint ENI
  │
  └── Other internet destination?
        └── NAT Gateway (default route)
  │
  │  Route selection is based on destination IP.
  │  DNS resolution happens before IP routing.
  │
  ▼
[N6] NETWORK ACCESS IS READY — BUT WHO HAS PERMISSION?
  │
  │  Being able to reach S3 does not automatically
  │  mean the application can download an object.
  │
  └── IAM EXECUTION ROLE
        │
        ├── returns-ml-sagemaker-role
        │
        ├── Allows approved SageMaker API actions
        │
        ├── Allows access to the configured S3 bucket
        │     ├── s3:ListBucket
        │     ├── s3:GetObject
        │     └── s3:PutObject
        │
        └── Principle:
              Network connectivity ≠ authorization
  │
  ▼
[P0] NOW CREATE THE SAGEMAKER DEVELOPMENT ENVIRONMENT
  │
  └── SAGEMAKER DOMAIN: returns-ml-domain
        │
        ├── Logical container for Studio configurations
        │
        ├── Authentication: IAM
        │
        ├── Network mode: VPC ONLY
        │     ├── Select returns-ml-vpc
        │     └── Select the two private subnets
        │
        ├── Configure execution role and application defaults
        │
        └── USER PROFILE: instructor
              │
              ▼
            SPACE
              │
              ├── Persistent workspace storage
              └── Development application:
                    JupyterLab / Code Editor
                    │
                    ▼
                  COMPUTE INSTANCE
                    │
                    ├── Executes Python code
                    ├── Reads datasets from S3
                    ├── Calls AWS APIs
                    └── Uses the configured VPC networking
  │
  ▼
[R0] FINAL CHECK — FOLLOW FOUR REAL REQUESTS
  │
  ├── REQUEST A: pip install pandas
  │     └── Private subnet → NAT → Internet
  │
  ├── REQUEST B: boto3 downloads a file from S3
  │     └── Private subnet → S3 Gateway Endpoint → S3
  │
  ├── REQUEST C: boto3 calls SageMaker API
  │     └── Private DNS → Interface Endpoint → SageMaker
  │
  └── REQUEST D: Application calls an external REST API
        └── Private subnet → NAT → Internet

END — Private ML development environment ready
```