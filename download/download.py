import boto3
import os
import requests

pdfs = [
    'https://docs.aws.amazon.com/pdfs/aws-certification/latest/security-specialty-03/security-specialty-03.pdf',
    'https://docs.aws.amazon.com/pdfs/athena/latest/ug/athena-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/opensearch-service/latest/developerguide/opensearch-service-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/sns/latest/dg/sns-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/step-functions/latest/dg/step-functions-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/apigateway/latest/developerguide/apigateway-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/AWSEC2/latest/UserGuide/ec2-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/imagebuilder/latest/userguide/imagebuilder-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/eks/latest/userguide/eks-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/emr/latest/ManagementGuide/emr-mgmt.pdf',
    'https://docs.aws.amazon.com/pdfs/lambda/latest/dg/lambda-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/fis/latest/userguide/fis-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/iot/latest/developerguide/iot-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/bedrock/latest/userguide/bedrock-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/codeguru/latest/profiler-ug/profiler-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/codeguru/latest/reviewer-ug/reviewer-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/amazonq/latest/qbusiness-ug/qbusiness-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/amazonq/latest/qdeveloper-ug/amazonq-developer-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/sagemaker/latest/dg/sagemaker-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/AWSCloudFormation/latest/UserGuide/cfn-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/awscloudtrail/latest/userguide/awscloudtrail-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/AmazonCloudWatch/latest/monitoring/acw-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/AmazonCloudWatch/latest/logs/cwl-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/eventbridge/latest/userguide/user-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/config/latest/developerguide/config-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/controltower/latest/userguide/controltower-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/grafana/latest/userguide/service-guide.pdf.pdf',
    'https://docs.aws.amazon.com/pdfs/organizations/latest/userguide/organizations-userguide.pdf',
    'https://docs.aws.amazon.com/pdfs/resilience-hub/latest/userguide/resilience-hub-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/resource-explorer/latest/userguide/resource_explorer_ug.pdf',
    'https://docs.aws.amazon.com/pdfs/servicecatalog/latest/adminguide/service-catalog-ag.pdf',
    'https://docs.aws.amazon.com/pdfs/systems-manager/latest/userguide/systems-manager-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/awssupport/latest/user/support-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/notifications/latest/userguide/notifications-guide.pdf.pdf',
    'https://docs.aws.amazon.com/pdfs/wellarchitected/latest/userguide/wellarchitected-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/r53recovery/latest/dg/r53-recovery-guide.pdf.pdf',
    'https://docs.aws.amazon.com/pdfs/vpc/latest/userguide/vpc-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/vpn/latest/s2svpn/s2s-vpn-user-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/verified-access/latest/ug/verified-access-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/vpn/latest/clientvpn-user/client-vpn-user-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/AmazonCloudFront/latest/DeveloperGuide/AmazonCloudFront_DevGuide.pdf',
    'https://docs.aws.amazon.com/pdfs/verifiedpermissions/latest/userguide/amazon-verified-permissions-user-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/Route53/latest/DeveloperGuide/route53-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/directconnect/latest/UserGuide/dc-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/elasticloadbalancing/latest/userguide/elb-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/vpc/latest/tgw/vpc-tgw.pdf',
    'https://docs.aws.amazon.com/pdfs/artifact/latest/ug/artifact-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/audit-manager/latest/userguide/audit-manager-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/acm/latest/userguide/acm-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/cloudhsm/latest/userguide/cloudhsm-user-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/cognito/latest/developerguide/cognito-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/detective/latest/userguide/detective-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/directoryservice/latest/admin-guide/directoryservice-admin-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/waf/latest/developerguide/waf-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/guardduty/latest/ug/guardduty-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/IAM/latest/UserGuide/iam-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/singlesignon/latest/userguide/sso-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/inspector/latest/user/inspector-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/kms/latest/developerguide/kms-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/macie/latest/user/macie-user-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/network-firewall/latest/developerguide/network-firewall-developer-guide.pdf',
    'https://docs.aws.amazon.com/pdfs/privateca/latest/userguide/privateca-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/secretsmanager/latest/userguide/secretsmanager-userguide.pdf',
    'https://docs.aws.amazon.com/pdfs/securityhub/latest/userguide/securityhub.pdf',
    'https://docs.aws.amazon.com/pdfs/security-lake/latest/userguide/security-lake-userguide.pdf',
    'https://docs.aws.amazon.com/pdfs/AmazonS3/latest/userguide/s3-userguide.pdf',
    'https://docs.aws.amazon.com/pdfs/aws-backup/latest/devguide/AWSBackup-dg.pdf',
    'https://docs.aws.amazon.com/pdfs/datasync/latest/userguide/datasync-userguide.pdf',
    'https://docs.aws.amazon.com/pdfs/efs/latest/ug/efs-ug.pdf',
    'https://docs.aws.amazon.com/pdfs/fsx/latest/FileCacheGuide/FileCacheGuide.pdf'
]

def handler(event, context):

    s3 = boto3.client('s3')
    bucket = os.environ['S3_BUCKET']

    downloaded = []
    failed = []

    for pdf in pdfs:

        parts = pdf.split('/pdfs/')[1].split('/')
        key = parts[0]+'/'+parts[-1]

        try:

            response = requests.get(pdf, stream = True, timeout = 60)

            if response.status_code != 200:
                print('FAILED '+str(response.status_code)+' '+pdf)
                failed.append(pdf)
                continue

            response.raw.decode_content = True

            s3.upload_fileobj(
                response.raw,
                bucket,
                key,
                ExtraArgs = {
                    'ContentType': 'application/pdf'
                }
            )

            print('UPLOADED '+key)
            downloaded.append(key)

        except Exception as e:
            print('ERROR '+pdf+' '+str(e))
            failed.append(pdf)

    return {
        'bucket': bucket,
        'downloaded': len(downloaded),
        'failed': failed
    }
