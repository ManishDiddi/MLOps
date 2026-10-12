
## Stage 1 — AWS: Why do we need cloud infrastructure?

Question to ask:

> Suppose I've developed a Python API on my laptop. It works perfectly. But now I want people anywhere in the world to access it, 24 hours a day.
>
> Can I just keep my laptop running all the time? What problems might I face?

Solution — AWS

We need a computer that remains available, has reliable infrastructure, and can host our application without depending on our personal laptop.

AWS provides computing resources over the internet. Instead of purchasing and maintaining physical servers, we can rent virtual servers using services such as EC2.

Transition: "Great! AWS gives us virtual servers. But where do we place these servers, and how do we organize their network?"

## Stage 2 — VPC: Why do we need our own network?

Question to ask:

> AWS has millions of customers running applications on its infrastructure.
>
> If we're going to launch our own servers on AWS, how do we create a network that we control? How do we decide which IP addresses our servers use and how they communicate?

Solution — VPC (Virtual Private Cloud)

A VPC is our own logically isolated network inside AWS.

Within this network, we can define private IP address ranges, organize resources, and control networking and connectivity.

For example, we create a VPC with the address range `10.0.0.0/16`.

Transition: "Now we have our own private network. But what if we want to organize our servers into different sections instead of keeping everything in one large network?"

## Stage 3 — Subnet: How do we organize our network?

Question to ask:

> Imagine our company has 100 servers. Some run applications, others run databases, and others perform background processing.
>
> Would it make sense to put every server into one large network section? What if we wanted to organize them into smaller groups, with different networking configurations?
>
> And what if we wanted our servers to run in different AWS Availability Zones?

Solution — Subnet

A subnet divides the VPC's IP address range into smaller, non-overlapping ranges.

For example:

- Subnet A: `10.0.1.0/24` in `us-west-2a`
- Subnet B: `10.0.2.0/24` in `us-west-2b`

Both belong to the same VPC, but each occupies a different Availability Zone.

This lets us organize resources and associate different routing configurations with different subnets.

Transition: "Excellent! We now have two subnets, and we've launched an EC2 instance in each. But there's a problem: someone outside AWS wants to access our Python API. How can they reach it?"

## Stage 4 — Internet Gateway: How does our VPC connect to the internet?

Question to ask:

> Our EC2 instance is running inside our VPC. Someone sitting at home wants to open our application in their browser.
>
> But our VPC is a private network. How do we connect this network to the public internet?

Solution — Internet Gateway

An Internet Gateway provides a connection between our VPC and the public internet.

We create an Internet Gateway and attach it to our VPC.

It supports traffic entering and leaving the VPC through the internet, provided that the necessary routing, addressing, and security requirements are satisfied.

Transition: "Okay, we've attached an Internet Gateway. But how does our network know whether traffic should stay within the VPC or go out through that gateway?"

## Stage 5 — Route Table: How does the network know where to send traffic?

Question to ask:

> Imagine our EC2 server wants to communicate with another server inside the same VPC.
>
> Now imagine it wants to communicate with a website on the public internet.
>
> These are two different destinations. How does AWS decide where to forward the network traffic?

Solution — Route Table

A route table contains rules that determine where network traffic should be directed based on its destination IP address.

For example:

| Destination   | Target             |
| ------------- | ------------------ |
| `10.0.0.0/16` | Local (inside VPC) |
| `0.0.0.0/0`   | Internet Gateway   |

When traffic is going to an address inside the VPC, the local route applies.

When traffic is going to another IPv4 destination, the default route sends it toward the Internet Gateway.

We associate this route table with both subnets, making them public subnets. Our EC2 instances also need public IPv4 addresses for direct IPv4 connectivity through the gateway.

Transition: "Now our EC2 instance has a public IP address, a route to the internet, and an Internet Gateway. But should that mean anyone can connect to every service running on our server?"

## Stage 6 — Security Group: Who is allowed to connect to our server?

Question to ask:

> Suppose our EC2 instance is running a Python API on port 8000.
>
> We want our own computer to access that API, but we don't want random people connecting to other services running on the server.
>
> How do we control which connections are permitted?

Solution — Security Group

A Security Group acts as a virtual firewall for resources such as EC2 instances.

It lets us define which inbound and outbound connections are allowed.

For example, we can configure a security group with this inbound rule:

| Protocol | Port | Source                |
| -------- | ---- | --------------------- |
| TCP      | 8000 | Our public IP address |

Now connections from our permitted IP address can reach the API on port 8000. Other new inbound connections remain blocked unless explicitly allowed by another rule.

Transition: "Now that we've configured all these components, can someone explain the complete journey of an HTTP request from our browser to the Python API running on EC2?"

## Stage 7 — Bring everything together

Final question to ask:

> I've created a VPC, divided it into two subnets, attached an Internet Gateway, configured a Route Table, and created a Security Group.
>
> My Python API is running on EC2 at port 8000.
>
> Now I enter `http://<public-ip>:8000` in my browser.
>
> Can you walk me through how that request reaches the application and how the response comes back?

Expected explanation:

The browser sends a request to the EC2 instance's public IP. The Internet Gateway provides the VPC's internet connectivity, while routing allows the traffic to reach the instance's network interface. The Security Group checks whether the inbound connection is permitted on port 8000.

If the rules allow the connection and the API is listening, the request reaches the application. The response travels back through the VPC's networking and the Internet Gateway to the browser. Because security groups are stateful, response traffic for an allowed connection is permitted automatically.

### The complete sequence at a glance

| Stage | Problem we introduce                                          | Component that solves it |
| ----- | ------------------------------------------------------------- | ------------------------ |
| 1     | How do we host our application without relying on our laptop? | AWS / EC2                |
| 2     | How do we create a network that we control?                   | VPC                      |
| 3     | How do we divide and organize that network?                   | Subnet                   |
| 4     | How do we connect our VPC to the public internet?             | Internet Gateway         |
| 5     | How does AWS know where to direct traffic?                    | Route Table              |
| 6     | How do we control who can connect to our server?              | Security Group           |
| 7     | How do all these components work together?                    | Complete architecture    |
