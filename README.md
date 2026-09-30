# AWS Security Specialty Study Kit

An AWS CDK project that collects the official AWS documentation PDFs relevant to the **AWS Certified Security - Specialty (SCS-C03)** exam.

The stack creates a private S3 bucket and a manually invoked Lambda function. Each invocation downloads the PDFs in `download/download.py` and stores them at the bucket root with names based on the study guide titles below, such as `amazon-guardduty.pdf`. A container Lambda converts PDFs uploaded to a separate PDF bucket into Markdown in a third bucket, and another container Lambda splits PDFs uploaded to a raw bucket into 1,000-page parts in a split bucket.

## What it deploys

| Resource | Configuration |
| --- | --- |
| S3 bucket | `scs-use2-lukach-io`, S3-managed encryption, public access blocked, SSL required |
| Lambda function | `scs-download`, Python 3.13, ARM64, 15-minute timeout, 1 GiB memory |
| PDF bucket | `pdf-use2-lukach-io`, private S3 bucket for manually uploaded PDFs |
| Markdown bucket | `md-use2-lukach-io`, private S3 bucket for converted Markdown |
| Container Lambda | `pdf2md`, Python 3.13 image with `pymupdf4llm`, x86_64, 15-minute timeout, 4 GiB memory |
| Raw bucket | `raw-use2-lukach-io`, private S3 bucket for large PDFs awaiting a split |
| Split bucket | `split-use2-lukach-io`, private S3 bucket for the split PDF parts |
| Container Lambda | `raw2split`, Python 3.13 image with `pymupdf`, x86_64, 15-minute timeout, 4 GiB memory |
| CloudWatch Logs | `/aws/lambda/scs-download`, `/aws/lambda/pdf2md`, and `/aws/lambda/raw2split`, one-month retention |

The bucket is configured for removal on stack deletion. Downloaded objects are replaced when the function runs again.

## Prerequisites

- AWS credentials configured for an account where you can deploy CDK resources
- AWS CDK v2 and Python 3.13+
- Node.js, required by the AWS CDK CLI
- Docker, running locally for the CDK container-image build
- An existing `packages-use2-lukach-io` bucket containing `requests.zip`

The Lambda layer expects `requests.zip` to contain the `requests` dependency and to be compatible with Python 3.13 on ARM64.

## Deploy

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cdk bootstrap
cdk deploy
```

The app is pinned to `us-east-2` in `app.py`. Deployment does not download or convert documents until the corresponding Lambda is invoked or a PDF is uploaded.

## Download the documents

Invoke the Lambda after deployment:

```bash
aws lambda invoke \
  --function-name scs-download \
  --region us-east-2 \
  response.json

cat response.json
```

The response includes the destination bucket, the number of successful downloads, and any URLs that failed:

```json
{
  "bucket": "scs-use2-lukach-io",
  "downloaded": 70,
  "failed": []
}
```

List or download the resulting files with the AWS CLI:

```bash
aws s3 ls s3://scs-use2-lukach-io/ --recursive
aws s3 sync s3://scs-use2-lukach-io/ ./pdfs
```

## Convert a PDF to Markdown

Upload a PDF to the input bucket to trigger conversion:

```bash
aws s3 cp ./input.pdf s3://pdf-use2-lukach-io/guides/input.pdf --region us-east-2
aws s3 cp s3://md-use2-lukach-io/guides/input.md ./input.md --region us-east-2
```

The Lambda writes the converted Markdown under the same folder path, replacing the `.pdf` extension with `.md`. Other uploaded file types are ignored. Existing Markdown at that key is overwritten if the PDF is uploaded again. The PDF and Markdown buckets are deleted with their contents when the stack is destroyed.

## Split a large PDF

Upload a PDF to the raw bucket to trigger `raw2split`:

```bash
aws s3 cp ./large.pdf s3://raw-use2-lukach-io/guides/large.pdf --region us-east-2
aws s3 ls s3://split-use2-lukach-io/ --region us-east-2
```

The Lambda splits the document into parts of 1,000 pages at most and writes them to the root of the split bucket, dropping any folder prefix. Each part keeps the source file name with a four-digit suffix, such as `large-0001.pdf` and `large-0002.pdf`, so sorting by name preserves the original page order. Documents of 1,000 pages or fewer still produce a single `-0001.pdf` part. Non-PDF uploads are ignored, and identically named PDFs in different raw folders overwrite each other in the split bucket.

## Project layout

```text
.
├── app.py                 # CDK application entry point
├── cdk.json               # CDK CLI configuration
├── download/download.py   # Lambda handler and document manifest
├── pdf2md/Dockerfile      # Container Lambda image with pymupdf4llm
├── pdf2md/pdf2md.py      # S3 event handler and PDF conversion
├── raw2split/Dockerfile   # Container Lambda image with pymupdf
├── raw2split/raw2split.py # S3 event handler and PDF splitting
├── scs/scs_stack.py       # Infrastructure definition
├── tests/test_pdf2md.py  # Conversion event test
├── tests/test_raw2split.py # Split event test
└── requirements.txt       # Python dependencies
```

## Study guide

The manifest contains the exam guide plus the following official AWS documentation. Links open the PDFs directly from AWS.

<details>
<summary><strong>Exam guide</strong></summary>

- [AWS Certified Security - Specialty (SCS-C03) exam guide](https://docs.aws.amazon.com/pdfs/aws-certification/latest/security-specialty-03/security-specialty-03.pdf)

</details>

<details>
<summary><strong>Analytics</strong></summary>

- [Amazon Athena](https://docs.aws.amazon.com/pdfs/athena/latest/ug/athena-ug.pdf)
- [Amazon OpenSearch Service](https://docs.aws.amazon.com/pdfs/opensearch-service/latest/developerguide/opensearch-service-dg.pdf)

</details>

<details>
<summary><strong>Application Integration</strong></summary>

- [Amazon SNS](https://docs.aws.amazon.com/pdfs/sns/latest/dg/sns-dg.pdf)
- [AWS Step Functions](https://docs.aws.amazon.com/pdfs/step-functions/latest/dg/step-functions-dg.pdf)

</details>

<details>
<summary><strong>Compute</strong></summary>

- [Amazon API Gateway](https://docs.aws.amazon.com/pdfs/apigateway/latest/developerguide/apigateway-dg.pdf)
- [Amazon EC2](https://docs.aws.amazon.com/pdfs/AWSEC2/latest/UserGuide/ec2-ug.pdf)
- [EC2 Image Builder](https://docs.aws.amazon.com/pdfs/imagebuilder/latest/userguide/imagebuilder-ug.pdf)
- [Amazon EKS](https://docs.aws.amazon.com/pdfs/eks/latest/userguide/eks-ug.pdf)
- [Amazon EMR](https://docs.aws.amazon.com/pdfs/emr/latest/ManagementGuide/emr-mgmt.pdf)
- [AWS Lambda](https://docs.aws.amazon.com/pdfs/lambda/latest/dg/lambda-dg.pdf)

</details>

<details>
<summary><strong>Developer Tools</strong></summary>

- [AWS Fault Injection Service](https://docs.aws.amazon.com/pdfs/fis/latest/userguide/fis-guide.pdf)

</details>

<details>
<summary><strong>Internet of Things</strong></summary>

- [AWS IoT Core](https://docs.aws.amazon.com/pdfs/iot/latest/developerguide/iot-dg.pdf)

</details>

<details>
<summary><strong>Machine Learning</strong></summary>

- [Amazon Bedrock](https://docs.aws.amazon.com/pdfs/bedrock/latest/userguide/bedrock-ug.pdf)
- [Amazon CodeGuru Profiler](https://docs.aws.amazon.com/pdfs/codeguru/latest/profiler-ug/profiler-ug.pdf)
- [Amazon CodeGuru Reviewer](https://docs.aws.amazon.com/pdfs/codeguru/latest/reviewer-ug/reviewer-ug.pdf)
- [Amazon Q Business](https://docs.aws.amazon.com/pdfs/amazonq/latest/qbusiness-ug/qbusiness-ug.pdf)
- [Amazon Q Developer](https://docs.aws.amazon.com/pdfs/amazonq/latest/qdeveloper-ug/amazonq-developer-ug.pdf)
- [Amazon SageMaker AI](https://docs.aws.amazon.com/pdfs/sagemaker/latest/dg/sagemaker-dg.pdf)

</details>

<details>
<summary><strong>Management and Governance</strong></summary>

- [AWS CloudFormation](https://docs.aws.amazon.com/pdfs/AWSCloudFormation/latest/UserGuide/cfn-ug.pdf)
- [AWS CloudTrail](https://docs.aws.amazon.com/pdfs/awscloudtrail/latest/userguide/awscloudtrail-ug.pdf)
- [Amazon CloudWatch monitoring](https://docs.aws.amazon.com/pdfs/AmazonCloudWatch/latest/monitoring/acw-ug.pdf)
- [Amazon CloudWatch Logs](https://docs.aws.amazon.com/pdfs/AmazonCloudWatch/latest/logs/cwl-ug.pdf)
- [Amazon EventBridge](https://docs.aws.amazon.com/pdfs/eventbridge/latest/userguide/user-guide.pdf)
- [AWS Config](https://docs.aws.amazon.com/pdfs/config/latest/developerguide/config-dg.pdf)
- [AWS Control Tower](https://docs.aws.amazon.com/pdfs/controltower/latest/userguide/controltower-ug.pdf)
- [Amazon Managed Grafana](https://docs.aws.amazon.com/pdfs/grafana/latest/userguide/service-guide.pdf.pdf)
- [AWS Organizations](https://docs.aws.amazon.com/pdfs/organizations/latest/userguide/organizations-userguide.pdf)
- [AWS Resilience Hub](https://docs.aws.amazon.com/pdfs/resilience-hub/latest/userguide/resilience-hub-guide.pdf)
- [AWS Resource Explorer](https://docs.aws.amazon.com/pdfs/resource-explorer/latest/userguide/resource_explorer_ug.pdf)
- [AWS Service Catalog](https://docs.aws.amazon.com/pdfs/servicecatalog/latest/adminguide/service-catalog-ag.pdf)
- [AWS Systems Manager](https://docs.aws.amazon.com/pdfs/systems-manager/latest/userguide/systems-manager-ug.pdf)
- [AWS Trusted Advisor](https://docs.aws.amazon.com/pdfs/awssupport/latest/user/support-ug.pdf)
- [AWS User Notifications](https://docs.aws.amazon.com/pdfs/notifications/latest/userguide/notifications-guide.pdf.pdf)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/pdfs/wellarchitected/latest/userguide/wellarchitected-ug.pdf)

</details>

<details>
<summary><strong>Networking and Content Delivery</strong></summary>

- [Amazon Application Recovery Controller](https://docs.aws.amazon.com/pdfs/r53recovery/latest/dg/r53-recovery-guide.pdf.pdf)
- [Amazon VPC](https://docs.aws.amazon.com/pdfs/vpc/latest/userguide/vpc-ug.pdf)
- [AWS Site-to-Site VPN](https://docs.aws.amazon.com/pdfs/vpn/latest/s2svpn/s2s-vpn-user-guide.pdf)
- [AWS Verified Access](https://docs.aws.amazon.com/pdfs/verified-access/latest/ug/verified-access-ug.pdf)
- [AWS Client VPN](https://docs.aws.amazon.com/pdfs/vpn/latest/clientvpn-user/client-vpn-user-guide.pdf)
- [Amazon CloudFront](https://docs.aws.amazon.com/pdfs/AmazonCloudFront/latest/DeveloperGuide/AmazonCloudFront_DevGuide.pdf)
- [Amazon Verified Permissions](https://docs.aws.amazon.com/pdfs/verifiedpermissions/latest/userguide/amazon-verified-permissions-user-guide.pdf)
- [Amazon Route 53](https://docs.aws.amazon.com/pdfs/Route53/latest/DeveloperGuide/route53-dg.pdf)
- [AWS Direct Connect](https://docs.aws.amazon.com/pdfs/directconnect/latest/UserGuide/dc-ug.pdf)
- [Elastic Load Balancing](https://docs.aws.amazon.com/pdfs/elasticloadbalancing/latest/userguide/elb-ug.pdf)
- [AWS Transit Gateway](https://docs.aws.amazon.com/pdfs/vpc/latest/tgw/vpc-tgw.pdf)

</details>

<details>
<summary><strong>Security, Identity, and Compliance</strong></summary>

- [AWS Artifact](https://docs.aws.amazon.com/pdfs/artifact/latest/ug/artifact-ug.pdf)
- [AWS Audit Manager](https://docs.aws.amazon.com/pdfs/audit-manager/latest/userguide/audit-manager-ug.pdf)
- [AWS Certificate Manager](https://docs.aws.amazon.com/pdfs/acm/latest/userguide/acm-ug.pdf)
- [AWS CloudHSM](https://docs.aws.amazon.com/pdfs/cloudhsm/latest/userguide/cloudhsm-user-guide.pdf)
- [Amazon Cognito](https://docs.aws.amazon.com/pdfs/cognito/latest/developerguide/cognito-dg.pdf)
- [Amazon Detective](https://docs.aws.amazon.com/pdfs/detective/latest/userguide/detective-ug.pdf)
- [AWS Directory Service](https://docs.aws.amazon.com/pdfs/directoryservice/latest/admin-guide/directoryservice-admin-guide.pdf)
- [AWS Firewall Manager](https://docs.aws.amazon.com/pdfs/waf/latest/developerguide/waf-dg.pdf)
- [Amazon GuardDuty](https://docs.aws.amazon.com/pdfs/guardduty/latest/ug/guardduty-ug.pdf)
- [AWS Identity and Access Management](https://docs.aws.amazon.com/pdfs/IAM/latest/UserGuide/iam-ug.pdf)
- [AWS IAM Identity Center](https://docs.aws.amazon.com/pdfs/singlesignon/latest/userguide/sso-ug.pdf)
- [Amazon Inspector](https://docs.aws.amazon.com/pdfs/inspector/latest/user/inspector-guide.pdf)
- [AWS Key Management Service](https://docs.aws.amazon.com/pdfs/kms/latest/developerguide/kms-dg.pdf)
- [Amazon Macie](https://docs.aws.amazon.com/pdfs/macie/latest/user/macie-user-guide.pdf)
- [AWS Network Firewall](https://docs.aws.amazon.com/pdfs/network-firewall/latest/developerguide/network-firewall-developer-guide.pdf)
- [AWS Private Certificate Authority](https://docs.aws.amazon.com/pdfs/privateca/latest/userguide/privateca-ug.pdf)
- [AWS Secrets Manager](https://docs.aws.amazon.com/pdfs/secretsmanager/latest/userguide/secretsmanager-userguide.pdf)
- [AWS Security Hub](https://docs.aws.amazon.com/pdfs/securityhub/latest/userguide/securityhub.pdf)
- [Amazon Security Lake](https://docs.aws.amazon.com/pdfs/security-lake/latest/userguide/security-lake-userguide.pdf)

</details>

<details>
<summary><strong>Storage and Data Management</strong></summary>

- [Amazon S3](https://docs.aws.amazon.com/pdfs/AmazonS3/latest/userguide/s3-userguide.pdf)
- [AWS Backup](https://docs.aws.amazon.com/pdfs/aws-backup/latest/devguide/AWSBackup-dg.pdf)
- [AWS DataSync](https://docs.aws.amazon.com/pdfs/datasync/latest/userguide/datasync-userguide.pdf)
- [Amazon EFS](https://docs.aws.amazon.com/pdfs/efs/latest/ug/efs-ug.pdf)
- [Amazon FSx for Lustre](https://docs.aws.amazon.com/pdfs/fsx/latest/FileCacheGuide/FileCacheGuide.pdf)

</details>

## Useful commands

```bash
cdk diff       # Review infrastructure changes
cdk synth      # Generate the CloudFormation template
cdk destroy    # Delete the stack and its bucket contents
```

The stack is intentionally focused on collecting documents. Edit the `pdfs` mapping of filename to URL in `download/download.py` to change the manifest.
