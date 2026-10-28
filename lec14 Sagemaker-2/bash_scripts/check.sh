
#!/bin/bash
# List every piece this class needs and say whether it is there. Only reads.
# Usage: bash check.sh YOUR-BUCKET-NAME
#BUCKET=${1:?usage: bash check.sh YOUR-BUCKET-NAME}
BUCKET="leviathan-bucket-v3"
export AWS_DEFAULT_REGION=us-west-2 AWS_REGION=us-west-2
# show NAME VALUE WANTED: MISSING if VALUE is empty, OK if its last word is WANTED, NOT-YET otherwise
show() {
  if [ -z "$2" ] || [ "$2" = "None" ]; then STATUS=MISSING
  elif [ -z "$3" ] || [ "${2##*[[:space:]]}" = "$3" ]; then STATUS=OK
  else STATUS=NOT-YET; fi
  printf '%-8s %-40s %s\n' "$STATUS" "$1" "$2"
}

VPC=$(aws ec2 describe-vpcs --filters Name=tag:Name,Values=leviathan-vpc --query 'Vpcs[0].VpcId' --output text)
show "VPC leviathan-vpc" "$VPC"
if [ "$VPC" = None ]; then
  # Everything below lives inside the VPC, so it cannot exist either.
  for NAME in "Internet gateway" "NAT gateway" "Endpoints" "Security groups"; do show "$NAME" ""; done
else
  IGW=$(aws ec2 describe-internet-gateways --filters Name=attachment.vpc-id,Values=$VPC --query 'InternetGateways[0].InternetGatewayId' --output text)
  show "Internet gateway" "$IGW"

  NAT=$(aws ec2 describe-nat-gateways --filter Name=vpc-id,Values=$VPC Name=state,Values=pending,available --query 'NatGateways[0].[NatGatewayId,State]' --output text)
  show "NAT gateway" "$NAT" available

  for SN in $(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC --query 'Subnets[].SubnetId' --output text); do
    RT=$(aws ec2 describe-route-tables --filters Name=association.subnet-id,Values=$SN --query 'RouteTables[0].RouteTableId' --output text)
    ROUTE=$(aws ec2 describe-route-tables --route-table-ids $RT --query "RouteTables[0].Routes[?DestinationCidrBlock=='0.0.0.0/0'].[NatGatewayId,State]" --output text)
    show "Internet route in $RT" "$ROUTE" active
  done

  for SERVICE in s3 sagemaker.api sagemaker.runtime sts logs ssm ssmmessages; do
    STATE=$(aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=$VPC Name=service-name,Values=com.amazonaws.us-west-2.$SERVICE \
      --query 'VpcEndpoints[?State!=`deleted` && State!=`deleting`]|[0].State' --output text)
    show "Endpoint $SERVICE" "$STATE" available
  done

  for GROUP in leviathan-studio-sg leviathan-endpoints-sg; do
    SG=$(aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC Name=group-name,Values=$GROUP --query 'SecurityGroups[0].GroupId' --output text)
    show "Security group $GROUP" "$SG"
  done
fi

ROLE=$(aws iam get-role --role-name leviathan-sagemaker-role --query Role.RoleName --output text 2>/dev/null)
show "Role" "$ROLE"
RA=$(aws iam get-role-policy --role-name leviathan-sagemaker-role --policy-name leviathan-remote-access \
  --query 'PolicyDocument.Statement[0].Action' --output text 2>/dev/null)
show "  remote-access policy (StartSession)" "$RA"
aws s3api head-bucket --bucket $BUCKET > /dev/null 2>&1 && show "Bucket $BUCKET" "found" || show "Bucket $BUCKET" ""
for KEY in raw/returns.csv train/train.csv validation/validation.csv batch-input/batch.csv batch-labels/labels.csv; do
  aws s3api head-object --bucket $BUCKET --key $KEY > /dev/null 2>&1 && show "  $KEY" "found" || show "  $KEY" ""
done

DOMAIN=$(aws sagemaker list-domains --query "Domains[?DomainName=='leviathan-domain' && Status!='Deleting']|[0].[DomainId,Status]" --output text)
show "Domain leviathan-domain" "$DOMAIN" InService
if [ "$DOMAIN" != None ]; then
  ID=${DOMAIN%%[[:space:]]*}
  show "User profile instructor" "$(aws sagemaker describe-user-profile --domain-id $ID --user-profile-name instructor --query Status --output text 2>/dev/null)" InService
  show "Space leviathan-lab" "$(aws sagemaker describe-space --domain-id $ID --space-name leviathan-lab --query Status --output text 2>/dev/null)" InService
  SPACE_ARN=$(aws sagemaker describe-space --domain-id $ID --space-name leviathan-lab --query SpaceArn --output text 2>/dev/null)
  [ -n "$SPACE_ARN" ] && TAG=$(aws sagemaker list-tags --resource-arn $SPACE_ARN --query "Tags[?Key=='sagemaker:user-profile-arn'].Value" --output text)
  show "  owner tag (needed for remote access)" "${TAG##*/}" instructor
else
  show "User profile instructor" ""; show "Space leviathan-lab" ""
fi

#bash check.sh YOUR-BUCKET-NAME
