
START — leviathan API: two EC2 instances, but no load balancer
  │
  ├── leviathan-ec2-a ─── us-west-2a · FastAPI on port 8000
  └── leviathan-ec2-b ─── us-west-2b · FastAPI on port 8000
  │
  │   Both instances run the same Docker image from ECR.
  │   Both expose GET /health, GET /, and prediction APIs.
  │
  ▼
[P0] THE PROBLEM — two machines, two public IP addresses
  │
  ├── Clients must know which instance to contact
  ├── If A stops, requests to A fail
  ├── B continues working, but clients must switch manually
  └── Restarting A can change its public IP address
  │
  ▼
[P1] INTRODUCE APPLICATION LOAD BALANCER (ALB)
     Goal: ONE public DNS name → MULTIPLE EC2 instances
  │
  │   Client → ALB → healthy EC2 instance
  │
  ▼
[P2] CREATE THE ALB SECURITY GROUP — leviathan-ec2-alb-sg
  │
  ├── Inbound: HTTP port 80 ← 0.0.0.0/0 (internet)
  ├── Outbound: allow traffic to backend instances
  └── Attached to the ALB, NOT to the EC2 instances
  │
  ▼
[P3] CREATE TARGET GROUP — leviathan-ec2-tg
  │
  ├── Target type: Instances
  ├── Protocol: HTTP
  ├── Backend port: 8000
  ├── Register both instances:
  │     ├── leviathan-ec2-a · us-west-2a
  │     └── leviathan-ec2-b · us-west-2b
  │
  └── HEALTH CHECK CONFIGURATION
        ├── Path: GET /health
        ├── Interval: 30 seconds
        ├── Timeout: 5 seconds
        ├── Healthy: 5 consecutive successful checks
        ├── Unhealthy: 2 consecutive failed checks
        └── Expected HTTP status: 200
  │
  ▼
[P4] CREATE THE ALB — leviathan-ec2-alb
  │
  ├── Type: Application Load Balancer (Layer 7)
  ├── Scheme: Internet-facing
  ├── VPC: leviathan-ec2-vpc
  ├── AZ us-west-2a → public subnet A
  ├── AZ us-west-2b → public subnet B
  ├── Security group: leviathan-ec2-alb-sg
  │
  └── LISTENER RULE
        HTTP port 80
             │
             ▼
        Forward to leviathan-ec2-tg (backend port 8000)
  │
  ▼
[P5] FIRST TEST — are both targets healthy?
  │
  ├── NO → BOTH TARGETS UNHEALTHY
  │         │
  │         ├── Health status: Request timed out
  │         ├── Client request to ALB → 504 Gateway Time-out
  │         │
  │         └── WHY?
  │              EC2 security group still allows port 8000
  │              only from "My IP", not from the ALB.
  │
  │         ▼
  │    [P5] FIX SECURITY GROUP — leviathan-ec2-host-sg
  │         │
  │         ├── Delete old port 8000 rule from My IP
  │         └── Add port 8000 rule:
  │                Source = leviathan-ec2-alb-sg
  │         │
  │         ▼
  │    Wait for health checks → both targets Healthy
  │
  └── YES → both targets Healthy
  │
  ▼
[P6] UNDERSTAND THE ACTUAL REQUEST FLOW
  │
  │     User sends GET http://ALB-DNS-NAME/
  │                      │
  │                      ▼
  │              Internet-facing ALB
  │                HTTP port 80
  │                      │
  │                      ▼
  │               Listener rule
  │             Forward to target group
  │                      │
  │                      ▼
  │          Which targets are Healthy?
  │                      │
  │             ┌────────┴────────┐
  │             ▼                 ▼
  │       EC2 instance A     EC2 instance B
  │       us-west-2a         us-west-2b
  │       HTTP :8000         HTTP :8000
  │             │                 │
  │             └────────┬────────┘
  │                      ▼
  │                FastAPI handles
  │                the request
  │                      │
  │                      ▼
  │              HTTP 200 response
  │           with served_by metadata
  │
  ▼
[P7] EXPERIMENT 1 — DOES LOAD BALANCING WORK?
  │
  ├── Send 10 requests to the SAME ALB DNS name
  │
  ├── Observe response metadata:
  │     ├── availability_zone: us-west-2a
  │     └── availability_zone: us-west-2b
  │
  ├── Actual experiment: 5 responses from A, 5 from B
  ├── Request order was not fixed
  └── Important: distribution is NOT guaranteed to be 50/50
  │
  ▼
[P8] EXPERIMENT 2 — STOP ONE EC2 INSTANCE
  │
  ├── Start continuous requests to the ALB DNS name
  │     └── Watch HTTP status codes every second
  │
  └── Stop leviathan-ec2-a
        │
        ▼
     What happens to requests?
        │
        ├── Initially: ALB may still try instance A
        │     ├── A has stopped responding
        │     ├── Health/state changes are not instantaneous
        │     └── Some requests fail (observed 502 and timeouts)
        │
        └── After detection (~40 seconds in the experiment)
              ├── Target A → Unused (instance stopped)
              ├── Target B → Healthy
              └── Requests → B only → HTTP 200
  │
  ▼
[P9] WHAT DID THE FAILURE EXPERIMENT PROVE?
  │
  ├── YES: the ALB routes around an unavailable instance
  ├── YES: clients keep using the SAME DNS name
  ├── YES: the second AZ can continue serving requests
  │
  ├── NO: failover is not necessarily instantaneous
  └── NO: the ALB does NOT create a replacement EC2
             └── Instance replacement needs EC2 Auto Scaling
  │
  ▼
[P10] HOW TO AVOID ERRORS DURING PLANNED MAINTENANCE?
  │
  ├── Don't immediately stop a healthy instance
  │
  └── Instead:
        1. Deregister target A from the target group
        2. Target enters Draining
        3. ALB stops sending new requests to A
        4. Allow existing requests to finish
        5. Stop instance A
        │
        ▼
     Remaining healthy target serves new requests
  │
  ▼
[P11] START THE INSTANCE AGAIN
  │
  ├── Start leviathan-ec2-a
  ├── Docker container restarts
  ├── Target state: Initial → Healthy
  ├── Health checks pass
  └── ALB resumes distributing requests to both instances
        │
        ├── No DNS changes required
        └── No target-group IP update required
             (targets registered by instance ID)
  │
  ▼
[P12] FINAL ARCHITECTURE
  │
  ├── ONE public DNS endpoint
  ├── TWO EC2 instances across two AZs
  ├── Health-check-based traffic routing
  ├── Instance access restricted to the ALB
  ├── Automatic routing around unhealthy targets
  └── NO automatic EC2 replacement (no Auto Scaling Group)
  │
  ▼
END — Application Load Balancer demonstrated successfully
