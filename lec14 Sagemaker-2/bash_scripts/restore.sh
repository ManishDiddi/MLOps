#!/bin/bash
# Bring the account to the state this class starts from: network, role, bucket and data, domain and space.
# It looks for each piece by name and creates only what is missing, so it is safe to run again.
# Usage: bash restore.sh YOUR-BUCKET-NAME
set -euo pipefail
#BUCKET=${1:?usage: bash restore.sh YOUR-BUCKET-NAME}
BUCKET="leviathan-bucket-v3"
export AWS_DEFAULT_REGION=us-west-2 AWS_REGION=us-west-2
DATA_URL="https://d2beiqkhq929f0.cloudfront.net/public_assets/assets/000/244/530/original/returns.csv?1791270327"
IMAGE="arn:aws:sagemaker:us-west-2:885854791233:image/sagemaker-distribution-cpu"
tag() { echo "ResourceType=$1,Tags=[{Key=Name,Value=$2}]"; }

# --- Network -------------------------------------------------------------------------------
VPC=$(aws ec2 describe-vpcs --filters Name=tag:Name,Values=leviathan-vpc --query 'Vpcs[0].VpcId' --output text)
if [ "$VPC" = None ]; then
  VPC=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 --tag-specifications "$(tag vpc leviathan-vpc)" --query Vpc.VpcId --output text)
  aws ec2 wait vpc-available --vpc-ids $VPC
  aws ec2 modify-vpc-attribute --vpc-id $VPC --enable-dns-support '{"Value":true}'
  aws ec2 modify-vpc-attribute --vpc-id $VPC --enable-dns-hostnames '{"Value":true}'
  echo "created VPC $VPC"
else echo "found   VPC $VPC"; fi

IGW=$(aws ec2 describe-internet-gateways --filters Name=attachment.vpc-id,Values=$VPC --query 'InternetGateways[0].InternetGatewayId' --output text)
if [ "$IGW" = None ]; then
  IGW=$(aws ec2 create-internet-gateway --tag-specifications "$(tag internet-gateway leviathan-igw)" --query InternetGateway.InternetGatewayId --output text)
  aws ec2 attach-internet-gateway --internet-gateway-id $IGW --vpc-id $VPC
  echo "created internet gateway $IGW"
else echo "found   internet gateway $IGW"; fi

# Use the VPC's own subnets if it has any (the previous class made two). Otherwise make two private ones.
SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC --query 'Subnets[].SubnetId' --output text)
if [ -z "$SUBNETS" ]; then
  i=1
  for AZ_CIDR in us-west-2b:10.0.128.0/20 us-west-2c:10.0.144.0/20; do
    AZ=${AZ_CIDR%%:*}; CIDR=${AZ_CIDR#*:}
    SN=$(aws ec2 create-subnet --vpc-id $VPC --cidr-block $CIDR --availability-zone $AZ \
         --tag-specifications "$(tag subnet leviathan-subnet-private$i-$AZ)" --query Subnet.SubnetId --output text)
    echo "created subnet $SN in $AZ"
    SUBNETS="$SUBNETS $SN"; i=$((i + 1))
  done
else echo "found   subnets" $SUBNETS; fi
RTS=""; i=1
for SN in $SUBNETS; do
  RT=$(aws ec2 describe-route-tables --filters Name=association.subnet-id,Values=$SN --query 'RouteTables[0].RouteTableId' --output text)
  if [ "$RT" = None ]; then
    AZ=$(aws ec2 describe-subnets --subnet-ids $SN --query 'Subnets[0].AvailabilityZone' --output text)
    RT=$(aws ec2 create-route-table --vpc-id $VPC --tag-specifications "$(tag route-table leviathan-rtb-private$i-$AZ)" \
         --query RouteTable.RouteTableId --output text)
    aws ec2 associate-route-table --route-table-id $RT --subnet-id $SN > /dev/null
    echo "created route table $RT for $SN"
  else echo "found   route table $RT for $SN"; fi
  RTS="$RTS $RT"; i=$((i + 1))
done

S3EP=$(aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=$VPC Name=service-name,Values=com.amazonaws.us-west-2.s3 \
       --query 'VpcEndpoints[?State!=`deleted` && State!=`deleting`]|[0].VpcEndpointId' --output text)
if [ "$S3EP" = None ]; then
  S3EP=$(aws ec2 create-vpc-endpoint --vpc-id $VPC --vpc-endpoint-type Gateway --service-name com.amazonaws.us-west-2.s3 \
         --route-table-ids $RTS --tag-specifications "$(tag vpc-endpoint leviathan-vpce-s3)" --query VpcEndpoint.VpcEndpointId --output text)
  echo "created S3 gateway endpoint $S3EP"
else echo "found   S3 gateway endpoint $S3EP"; fi

sg() { aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC Name=group-name,Values=$1 --query 'SecurityGroups[0].GroupId' --output text; }
STUDIO=$(sg leviathan-studio-sg)
if [ "$STUDIO" = None ]; then
  STUDIO=$(aws ec2 create-security-group --vpc-id $VPC --group-name leviathan-studio-sg --description "Studio domain and its spaces" --query GroupId --output text)
  aws ec2 authorize-security-group-ingress --group-id $STUDIO --ip-permissions "IpProtocol=tcp,FromPort=0,ToPort=65535,UserIdGroupPairs=[{GroupId=$STUDIO}]" > /dev/null
  echo "created security group leviathan-studio-sg $STUDIO"
else echo "found   security group leviathan-studio-sg $STUDIO"; fi
ENDP=$(sg leviathan-endpoints-sg)
if [ "$ENDP" = None ]; then
  ENDP=$(aws ec2 create-security-group --vpc-id $VPC --group-name leviathan-endpoints-sg --description "Interface endpoints, HTTPS from Studio" --query GroupId --output text)
  aws ec2 authorize-security-group-ingress --group-id $ENDP --ip-permissions "IpProtocol=tcp,FromPort=443,ToPort=443,UserIdGroupPairs=[{GroupId=$STUDIO}]" > /dev/null
  echo "created security group leviathan-endpoints-sg $ENDP"
else echo "found   security group leviathan-endpoints-sg $ENDP"; fi

NAT=$(aws ec2 describe-nat-gateways --filter Name=vpc-id,Values=$VPC Name=state,Values=pending,available --query 'NatGateways[0].NatGatewayId' --output text)
if [ "$NAT" = None ]; then
  NAT=$(aws ec2 create-nat-gateway --vpc-id $VPC --availability-mode regional \
        --tag-specifications "$(tag natgateway leviathan-regional-nat)" --query NatGateway.NatGatewayId --output text)
  echo "created NAT gateway $NAT, waiting for it (two to three minutes)"
else echo "found   NAT gateway $NAT"; fi
aws ec2 wait nat-gateway-available --nat-gateway-ids $NAT

for RT in $RTS; do
  NOW=$(aws ec2 describe-route-tables --route-table-ids $RT --query "RouteTables[0].Routes[?DestinationCidrBlock=='0.0.0.0/0'].[NatGatewayId,State]" --output text)
  if [ -z "$NOW" ]; then
    aws ec2 create-route --route-table-id $RT --destination-cidr-block 0.0.0.0/0 --nat-gateway-id $NAT > /dev/null
    echo "created route in $RT to $NAT"
  elif [ "$NOW" != "$(printf '%s\tactive' $NAT)" ]; then
    aws ec2 replace-route --route-table-id $RT --destination-cidr-block 0.0.0.0/0 --nat-gateway-id $NAT
    echo "pointed route in $RT at $NAT (it was: $NOW)"
  else echo "found   route in $RT to $NAT"; fi
done

for SERVICE in sagemaker.api sagemaker.runtime sts logs ssm ssmmessages; do
  EP=$(aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=$VPC Name=service-name,Values=com.amazonaws.us-west-2.$SERVICE \
       --query 'VpcEndpoints[?State!=`deleted` && State!=`deleting`]|[0].VpcEndpointId' --output text)
  if [ "$EP" = None ]; then
    EP=$(aws ec2 create-vpc-endpoint --vpc-id $VPC --vpc-endpoint-type Interface \
         --service-name com.amazonaws.us-west-2.$SERVICE --subnet-ids $SUBNETS \
         --security-group-ids $ENDP --private-dns-enabled \
         --tag-specifications "$(tag vpc-endpoint leviathan-$SERVICE)" --query VpcEndpoint.VpcEndpointId --output text)
    echo "created endpoint $SERVICE $EP"
  else echo "found   endpoint $SERVICE $EP"; fi
done

# --- Role ----------------------------------------------------------------------------------
ROLE=leviathan-sagemaker-role
if ! aws iam get-role --role-name $ROLE > /dev/null 2>&1; then
  aws iam create-role --role-name $ROLE --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"sagemaker.amazonaws.com"},"Action":"sts:AssumeRole"}]}' > /dev/null
  for P in AmazonSageMakerFullAccess AmazonSageMakerCanvasFullAccess AmazonSageMakerCanvasDataPrepFullAccess; do
    aws iam attach-role-policy --role-name $ROLE --policy-arn arn:aws:iam::aws:policy/$P
  done
  echo "created role $ROLE, waiting 15 s for IAM to catch up"; sleep 15
else echo "found   role $ROLE"; fi
# Always rewritten too. A role left over from an earlier run may lack it, and without
# sagemaker:StartSession the space refuses VS Code with "Remote access denied".
aws iam put-role-policy --role-name $ROLE --policy-name leviathan-remote-access --policy-document \
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["sagemaker:StartSession"],"Resource":"arn:*:sagemaker:*:*:space/${sagemaker:DomainId}/*","Condition":{"ArnLike":{"sagemaker:ResourceTag/sagemaker:user-profile-arn":"arn:aws:sagemaker:*:*:user-profile/${sagemaker:DomainId}/${sagemaker:UserProfileName}"}}}]}'
# Always rewritten, so the role names the bucket you passed in.
aws iam put-role-policy --role-name $ROLE --policy-name leviathan-bucket-access --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:ListBucket\",\"s3:GetBucketLocation\"],\"Resource\":\"arn:aws:s3:::$BUCKET\"},{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:DeleteObject\"],\"Resource\":\"arn:aws:s3:::$BUCKET/*\"}]}"
ROLE_ARN=$(aws iam get-role --role-name $ROLE --query Role.Arn --output text)

# --- Bucket and data -----------------------------------------------------------------------
if ! aws s3api head-bucket --bucket $BUCKET > /dev/null 2>&1; then
  aws s3 mb s3://$BUCKET > /dev/null; echo "created bucket $BUCKET"
else echo "found   bucket $BUCKET"; fi
if ! aws s3api head-object --bucket $BUCKET --key raw/returns.csv > /dev/null 2>&1; then
  curl -sf "$DATA_URL" | aws s3 cp - s3://$BUCKET/raw/returns.csv; echo "uploaded raw/returns.csv"
else echo "found   raw/returns.csv"; fi
if ! aws s3api head-object --bucket $BUCKET --key train/train.csv > /dev/null 2>&1; then
  echo "preparing the four files, as prepare.py did in the previous class"
  python3 -m venv /tmp/restore-venv && /tmp/restore-venv/bin/pip install -q pandas boto3
  BUCKET=$BUCKET /tmp/restore-venv/bin/python - <<'PY'
import os, boto3, pandas as pd
BUCKET = os.environ["BUCKET"]
s3 = boto3.client("s3")
raw = pd.read_csv(s3.get_object(Bucket=BUCKET, Key="raw/returns.csv")["Body"])
features = raw.drop(columns=["order_id", "order_date", "refund_amount", "returned"])
features = pd.get_dummies(features, columns=["category", "payment_method"], dtype=int)
data = pd.concat([raw["returned"], features], axis=1).sample(frac=1, random_state=0)
n = len(data)
train, validation, batch = data.iloc[: int(n * 0.7)], data.iloc[int(n * 0.7): int(n * 0.85)], data.iloc[int(n * 0.85):]
put = lambda df, key, header=False: s3.put_object(Bucket=BUCKET, Key=key, Body=df.to_csv(header=header, index=False))
put(train, "train/train.csv"); put(validation, "validation/validation.csv")
put(batch.drop(columns=["returned"]), "batch-input/batch.csv"); put(batch[["returned"]], "batch-labels/labels.csv", header=True)
print("wrote train", train.shape, "validation", validation.shape, "batch", batch.shape)
PY
else echo "found   train/train.csv and the other prepared files"; fi

# --- Domain, user profile and space ----------------------------------------------------------
# Idle shutdown is 180 minutes: work over the remote connection does not count as use, and this class runs long jobs.
DOMAIN=$(aws sagemaker list-domains --query "Domains[?DomainName=='leviathan-domain' && Status!='Deleting']|[0].DomainId" --output text)
if [ "$DOMAIN" = None ]; then
  DOMAIN=$(aws sagemaker create-domain --domain-name leviathan-domain --auth-mode IAM --vpc-id $VPC --subnet-ids $SUBNETS \
    --app-network-access-type VpcOnly \
    --default-user-settings "{\"ExecutionRole\":\"$ROLE_ARN\",\"SecurityGroups\":[\"$STUDIO\"],\"JupyterLabAppSettings\":{\"AppLifecycleManagement\":{\"IdleSettings\":{\"LifecycleManagement\":\"ENABLED\",\"IdleTimeoutInMinutes\":180}}}}" \
    --default-space-settings "{\"ExecutionRole\":\"$ROLE_ARN\",\"SecurityGroups\":[\"$STUDIO\"]}" \
    --query DomainArn --output text | cut -d/ -f2)
  echo "created domain $DOMAIN, waiting for it"
else echo "found   domain $DOMAIN"; fi
until [ "$(aws sagemaker describe-domain --domain-id $DOMAIN --query Status --output text)" = InService ]; do sleep 10; done

if ! aws sagemaker describe-user-profile --domain-id $DOMAIN --user-profile-name instructor > /dev/null 2>&1; then
  aws sagemaker create-user-profile --domain-id $DOMAIN --user-profile-name instructor > /dev/null
  echo "created user profile instructor"
else echo "found   user profile instructor"; fi
until [ "$(aws sagemaker describe-user-profile --domain-id $DOMAIN --user-profile-name instructor --query Status --output text)" = InService ]; do sleep 5; done

if ! aws sagemaker describe-space --domain-id $DOMAIN --space-name leviathan-lab > /dev/null 2>&1; then
  aws sagemaker create-space --domain-id $DOMAIN --space-name leviathan-lab \
    --ownership-settings OwnerUserProfileName=instructor --space-sharing-settings SharingType=Private \
    --space-settings "{\"AppType\":\"JupyterLab\",\"RemoteAccess\":\"ENABLED\",\"SpaceStorageSettings\":{\"EbsStorageSettings\":{\"EbsVolumeSizeInGb\":5}},\"JupyterLabAppSettings\":{\"DefaultResourceSpec\":{\"InstanceType\":\"ml.m5.large\",\"SageMakerImageArn\":\"$IMAGE\",\"SageMakerImageVersionAlias\":\"4.5.0\"}}}" > /dev/null
  echo "created space leviathan-lab (ml.m5.large, remote access on, stopped)"
else echo "found   space leviathan-lab"; fi
# The remote-access policy only allows spaces tagged with their owner's profile. The console adds
# this tag, create-space does not, and without it VS Code gets "Remote access denied".
aws sagemaker add-tags --resource-arn $(aws sagemaker describe-space --domain-id $DOMAIN --space-name leviathan-lab --query SpaceArn --output text) \
  --tags Key=sagemaker:user-profile-arn,Value=$(aws sagemaker describe-user-profile --domain-id $DOMAIN --user-profile-name instructor --query UserProfileArn --output text) > /dev/null
echo "done. Interface endpoints can take another minute to become available. Run check.sh."