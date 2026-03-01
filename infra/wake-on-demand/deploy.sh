#!/usr/bin/env bash
# deploy.sh — One-shot deployment for prisma-erp Wake-on-Demand
# Run from local machine (Windows Git Bash / WSL / Linux).
# Prerequisites: aws CLI configured, jq installed.
#
# Usage:
#   bash infra/wake-on-demand/deploy.sh
#
# After running, complete Steps 5 & 6 manually (DNS + EC2 SSH setup).

set -euo pipefail

REGION="ap-southeast-1"
INSTANCE_ID="i-0689ed2e9d9089d0d"
ACCOUNT_ID="704444257237"
DOMAIN="prismaerp.mywire.org"
LAMBDA_NAME="prisma-erp-wake"
IAM_ROLE="prisma-erp-wake"
IAM_POLICY="prisma-erp-ec2-wake"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Step 1: Elastic IP ==="
# Check if EIP already allocated for this instance
EXISTING_EIP=$(aws ec2 describe-addresses --region "$REGION" \
  --filters "Name=instance-id,Values=$INSTANCE_ID" \
  --query 'Addresses[0].PublicIp' --output text 2>/dev/null || echo "None")

if [ "$EXISTING_EIP" = "None" ] || [ -z "$EXISTING_EIP" ]; then
    EIP_ALLOC=$(aws ec2 allocate-address --region "$REGION" --domain vpc \
      --query AllocationId --output text)
    aws ec2 associate-address --region "$REGION" \
      --instance-id "$INSTANCE_ID" --allocation-id "$EIP_ALLOC"
    ELASTIC_IP=$(aws ec2 describe-addresses --region "$REGION" \
      --allocation-ids "$EIP_ALLOC" --query 'Addresses[0].PublicIp' --output text)
    echo "  Allocated new Elastic IP: $ELASTIC_IP (AllocationId: $EIP_ALLOC)"
else
    ELASTIC_IP="$EXISTING_EIP"
    echo "  Existing Elastic IP: $ELASTIC_IP"
fi

echo ""
echo "  >>> ACTION REQUIRED: Update Dynu A record for $DOMAIN to $ELASTIC_IP"
echo "  (Do this now or after CloudFront is ready)"
echo ""

echo "=== Step 2: IAM Role + Lambda ==="

# Create IAM role (idempotent: skip if exists)
ROLE_ARN=$(aws iam get-role --role-name "$IAM_ROLE" \
  --query 'Role.Arn' --output text 2>/dev/null || true)

if [ -z "$ROLE_ARN" ]; then
    ROLE_ARN=$(aws iam create-role --role-name "$IAM_ROLE" \
      --assume-role-policy-document '{
        "Version":"2012-10-17",
        "Statement":[{
          "Effect":"Allow",
          "Principal":{"Service":"lambda.amazonaws.com"},
          "Action":"sts:AssumeRole"
        }]
      }' --query 'Role.Arn' --output text)
    echo "  Created IAM role: $ROLE_ARN"
    aws iam attach-role-policy --role-name "$IAM_ROLE" \
      --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
else
    echo "  IAM role exists: $ROLE_ARN"
fi

# Create EC2 policy (idempotent: skip if exists)
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${IAM_POLICY}"
aws iam get-policy --policy-arn "$POLICY_ARN" >/dev/null 2>&1 || \
  aws iam create-policy --policy-name "$IAM_POLICY" \
    --policy-document "file://${SCRIPT_DIR}/iam-policy.json" >/dev/null

aws iam attach-role-policy --role-name "$IAM_ROLE" \
  --policy-arn "$POLICY_ARN" 2>/dev/null || true

echo "  Waiting 12s for role propagation..."
sleep 12

# Package Lambda
cd "$SCRIPT_DIR"
zip -q lambda.zip lambda_function.py
echo "  Packaged lambda.zip"

# Create or update Lambda function
LAMBDA_EXISTS=$(aws lambda get-function --function-name "$LAMBDA_NAME" \
  --region "$REGION" --query 'Configuration.FunctionArn' --output text 2>/dev/null || true)

if [ -z "$LAMBDA_EXISTS" ]; then
    LAMBDA_ARN=$(aws lambda create-function \
      --function-name "$LAMBDA_NAME" \
      --runtime python3.12 \
      --role "$ROLE_ARN" \
      --handler lambda_function.lambda_handler \
      --zip-file fileb://lambda.zip \
      --region "$REGION" \
      --timeout 15 \
      --environment "Variables={INSTANCE_ID=${INSTANCE_ID},REGION=${REGION},SITE_URL=https://${DOMAIN}}" \
      --query 'FunctionArn' --output text)
    echo "  Created Lambda: $LAMBDA_ARN"
else
    aws lambda update-function-code --function-name "$LAMBDA_NAME" \
      --zip-file fileb://lambda.zip --region "$REGION" >/dev/null
    aws lambda update-function-configuration --function-name "$LAMBDA_NAME" \
      --region "$REGION" \
      --environment "Variables={INSTANCE_ID=${INSTANCE_ID},REGION=${REGION},SITE_URL=https://${DOMAIN}}" \
      >/dev/null
    echo "  Updated Lambda code + config"
    LAMBDA_ARN="$LAMBDA_EXISTS"
fi

# Enable Lambda Function URL (for client JS to call directly)
LAMBDA_URL=$(aws lambda get-function-url-config --function-name "$LAMBDA_NAME" \
  --region "$REGION" --query 'FunctionUrl' --output text 2>/dev/null | sed 's|/$||' || true)

if [ -z "$LAMBDA_URL" ]; then
    aws lambda create-function-url-config \
      --function-name "$LAMBDA_NAME" \
      --region "$REGION" \
      --auth-type NONE \
      --cors '{"AllowOrigins":["*"],"AllowMethods":["GET","POST","OPTIONS"]}' >/dev/null
    aws lambda add-permission \
      --function-name "$LAMBDA_NAME" \
      --region "$REGION" \
      --statement-id FunctionURLAllowPublic \
      --action lambda:InvokeFunctionUrl \
      --principal '*' \
      --function-url-auth-type NONE >/dev/null
    LAMBDA_URL=$(aws lambda get-function-url-config --function-name "$LAMBDA_NAME" \
      --region "$REGION" --query 'FunctionUrl' --output text | sed 's|/$||')
    echo "  Lambda Function URL: $LAMBDA_URL"
else
    echo "  Lambda Function URL (existing): $LAMBDA_URL"
fi

# Strip trailing slash for consistent use
LAMBDA_URL="${LAMBDA_URL%/}"
LAMBDA_DOMAIN="${LAMBDA_URL#https://}"

echo ""
echo "=== Step 3: ACM Certificate (us-east-1 for CloudFront) ==="

# Check for existing cert
CERT_ARN=$(aws acm list-certificates --region us-east-1 \
  --query "CertificateSummaryList[?DomainName=='${DOMAIN}'].CertificateArn" \
  --output text 2>/dev/null || true)

if [ -z "$CERT_ARN" ]; then
    CERT_ARN=$(aws acm request-certificate \
      --region us-east-1 \
      --domain-name "$DOMAIN" \
      --validation-method DNS \
      --query CertificateArn --output text)
    echo "  Requested cert: $CERT_ARN"
else
    echo "  Existing cert: $CERT_ARN"
fi

echo ""
echo "  Fetching DNS validation record..."
sleep 5
DNS_VAL=$(aws acm describe-certificate --region us-east-1 \
  --certificate-arn "$CERT_ARN" \
  --query 'Certificate.DomainValidationOptions[0].ResourceRecord' 2>/dev/null || echo "pending")

echo "  >>> ACTION REQUIRED: Add this CNAME in Dynu for cert validation:"
echo "  $DNS_VAL"
echo "  Then wait 2-5 min for validation before proceeding to Step 4."
echo ""

# Wait for cert validation
echo "  Waiting up to 10 min for cert validation (Ctrl+C to skip and run step 4 separately)..."
for i in $(seq 1 20); do
    STATUS=$(aws acm describe-certificate --region us-east-1 \
      --certificate-arn "$CERT_ARN" \
      --query 'Certificate.Status' --output text 2>/dev/null || echo "PENDING_VALIDATION")
    echo "  [${i}/20] Cert status: $STATUS"
    if [ "$STATUS" = "ISSUED" ]; then
        echo "  Cert validated!"
        break
    fi
    sleep 30
done

echo ""
echo "=== Step 4: CloudFront Distribution ==="

# Check if distribution already exists
CF_DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Aliases.Items[?@=='${DOMAIN}']].Id" \
  --output text 2>/dev/null || true)

if [ -n "$CF_DIST_ID" ]; then
    echo "  CloudFront distribution already exists: $CF_DIST_ID"
    CF_DOMAIN=$(aws cloudfront get-distribution --id "$CF_DIST_ID" \
      --query 'Distribution.DomainName' --output text)
    echo "  CloudFront domain: $CF_DOMAIN"
else
    # Build distribution config JSON
    CALLER_REF="prisma-erp-$(date +%s)"
    CF_CONFIG=$(cat <<EOF
{
  "CallerReference": "${CALLER_REF}",
  "Aliases": {
    "Quantity": 1,
    "Items": ["${DOMAIN}"]
  },
  "Comment": "prisma-erp wake-on-demand",
  "Origins": {
    "Quantity": 2,
    "Items": [
      {
        "Id": "EC2Origin",
        "DomainName": "${ELASTIC_IP}",
        "CustomOriginConfig": {
          "HTTPPort": 8080,
          "HTTPSPort": 443,
          "OriginProtocolPolicy": "http-only",
          "OriginReadTimeout": 30,
          "OriginKeepaliveTimeout": 5,
          "OriginSSLProtocols": {
            "Quantity": 1,
            "Items": ["TLSv1.2"]
          }
        },
        "ConnectionAttempts": 1,
        "ConnectionTimeout": 10
      },
      {
        "Id": "LambdaOrigin",
        "DomainName": "${LAMBDA_DOMAIN}",
        "CustomOriginConfig": {
          "HTTPPort": 80,
          "HTTPSPort": 443,
          "OriginProtocolPolicy": "https-only",
          "OriginReadTimeout": 30,
          "OriginKeepaliveTimeout": 5,
          "OriginSSLProtocols": {
            "Quantity": 1,
            "Items": ["TLSv1.2"]
          }
        },
        "ConnectionAttempts": 1,
        "ConnectionTimeout": 10
      }
    ]
  },
  "OriginGroups": {
    "Quantity": 1,
    "Items": [
      {
        "Id": "EC2WithLambdaFailover",
        "FailoverCriteria": {
          "StatusCodes": {
            "Quantity": 5,
            "Items": [500, 502, 503, 504, 0]
          }
        },
        "Members": {
          "Quantity": 2,
          "Items": [
            {"OriginId": "EC2Origin"},
            {"OriginId": "LambdaOrigin"}
          ]
        }
      }
    ]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "EC2WithLambdaFailover",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 7,
      "Items": ["GET","HEAD","OPTIONS","PUT","POST","PATCH","DELETE"],
      "CachedMethods": {
        "Quantity": 2,
        "Items": ["GET","HEAD"]
      }
    },
    "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac",
    "Compress": true
  },
  "PriceClass": "PriceClass_200",
  "Enabled": true,
  "ViewerCertificate": {
    "ACMCertificateArn": "${CERT_ARN}",
    "SSLSupportMethod": "sni-only",
    "MinimumProtocolVersion": "TLSv1.2_2021"
  },
  "HttpVersion": "http2and3",
  "IsIPV6Enabled": true
}
EOF
)

    CF_RESULT=$(aws cloudfront create-distribution \
      --distribution-config "$CF_CONFIG" \
      --query '[Distribution.Id, Distribution.DomainName]' \
      --output text)
    CF_DIST_ID=$(echo "$CF_RESULT" | awk '{print $1}')
    CF_DOMAIN=$(echo "$CF_RESULT" | awk '{print $2}')
    echo "  Created CloudFront distribution: $CF_DIST_ID"
    echo "  CloudFront domain: $CF_DOMAIN"
fi

echo ""
echo "========================================"
echo "DEPLOYMENT COMPLETE"
echo "========================================"
echo ""
echo "Elastic IP:        $ELASTIC_IP"
echo "Lambda URL:        $LAMBDA_URL"
echo "CloudFront domain: $CF_DOMAIN"
echo "Cert ARN:          $CERT_ARN"
echo ""
echo "=== NEXT STEPS (manual) ==="
echo ""
echo "Step 5 — DNS (in Dynu web panel):"
echo "  a) Add cert validation CNAME (shown above in Step 3 output)"
echo "  b) Change A record for $DOMAIN → $ELASTIC_IP  (immediate access)"
echo "  c) After CloudFront propagates (~15 min): change to CNAME → $CF_DOMAIN"
echo ""
echo "Step 6 — EC2 SSH setup:"
echo "  ssh -i prisma-erp-key.pem ubuntu@$ELASTIC_IP \\"
echo "    'cd prisma-erp && git pull && \\"
echo "     sudo cp infra/wake-on-demand/prisma-erp-docker.service /etc/systemd/system/ && \\"
echo "     sudo systemctl daemon-reload && sudo systemctl enable prisma-erp-docker && \\"
echo "     chmod +x infra/wake-on-demand/auto-stop.sh && \\"
echo "     echo \"ubuntu ALL=(ALL) NOPASSWD: /sbin/shutdown\" | sudo tee /etc/sudoers.d/auto-stop && \\"
echo "     sudo chmod 440 /etc/sudoers.d/auto-stop && \\"
echo "     (crontab -l 2>/dev/null; echo \"*/5 * * * * /home/ubuntu/prisma-erp/infra/wake-on-demand/auto-stop.sh >> /var/log/auto-stop.log 2>&1\") | crontab -'"
echo ""
echo "=== VERIFICATION ==="
echo "  1. Auto-stop: ssh in, set IDLE_MIN=1 in auto-stop.sh, check /var/log/auto-stop.log"
echo "  2. Wake page:  stop EC2, visit https://$DOMAIN — should see 'Starting' page"
echo "  3. Lambda wake: wait ~3 min — page should auto-redirect to ERPNext"
echo "  4. Boot-on-start: start EC2 from console, wait 3 min, visit site"
