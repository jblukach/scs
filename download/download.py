import boto3
import os
import requests

pdfs = {
    'aws-certified-security-specialty-scs-c03-exam-guide.pdf': 'https://docs.aws.amazon.com/pdfs/aws-certification/latest/security-specialty-03/security-specialty-03.pdf',
    'amazon-athena.pdf': 'https://docs.aws.amazon.com/pdfs/athena/latest/ug/athena-ug.pdf',
    'amazon-opensearch-service.pdf': 'https://docs.aws.amazon.com/pdfs/opensearch-service/latest/developerguide/opensearch-service-dg.pdf',
    'amazon-sns.pdf': 'https://docs.aws.amazon.com/pdfs/sns/latest/dg/sns-dg.pdf',
    'aws-step-functions.pdf': 'https://docs.aws.amazon.com/pdfs/step-functions/latest/dg/step-functions-dg.pdf',
    'amazon-api-gateway.pdf': 'https://docs.aws.amazon.com/pdfs/apigateway/latest/developerguide/apigateway-dg.pdf',
    'amazon-ec2.pdf': 'https://docs.aws.amazon.com/pdfs/AWSEC2/latest/UserGuide/ec2-ug.pdf',
    'ec2-image-builder.pdf': 'https://docs.aws.amazon.com/pdfs/imagebuilder/latest/userguide/imagebuilder-ug.pdf',
    'amazon-eks.pdf': 'https://docs.aws.amazon.com/pdfs/eks/latest/userguide/eks-ug.pdf',
    'amazon-emr.pdf': 'https://docs.aws.amazon.com/pdfs/emr/latest/ManagementGuide/emr-mgmt.pdf',
    'aws-lambda.pdf': 'https://docs.aws.amazon.com/pdfs/lambda/latest/dg/lambda-dg.pdf',
    'aws-fault-injection-service.pdf': 'https://docs.aws.amazon.com/pdfs/fis/latest/userguide/fis-guide.pdf',
    'aws-iot-core.pdf': 'https://docs.aws.amazon.com/pdfs/iot/latest/developerguide/iot-dg.pdf',
    'amazon-bedrock.pdf': 'https://docs.aws.amazon.com/pdfs/bedrock/latest/userguide/bedrock-ug.pdf',
    'amazon-codeguru-profiler.pdf': 'https://docs.aws.amazon.com/pdfs/codeguru/latest/profiler-ug/profiler-ug.pdf',
    'amazon-codeguru-reviewer.pdf': 'https://docs.aws.amazon.com/pdfs/codeguru/latest/reviewer-ug/reviewer-ug.pdf',
    'amazon-q-business.pdf': 'https://docs.aws.amazon.com/pdfs/amazonq/latest/qbusiness-ug/qbusiness-ug.pdf',
    'amazon-q-developer.pdf': 'https://docs.aws.amazon.com/pdfs/amazonq/latest/qdeveloper-ug/amazonq-developer-ug.pdf',
    'amazon-sagemaker-ai.pdf': 'https://docs.aws.amazon.com/pdfs/sagemaker/latest/dg/sagemaker-dg.pdf',
    'aws-cloudformation.pdf': 'https://docs.aws.amazon.com/pdfs/AWSCloudFormation/latest/UserGuide/cfn-ug.pdf',
    'aws-cloudtrail.pdf': 'https://docs.aws.amazon.com/pdfs/awscloudtrail/latest/userguide/awscloudtrail-ug.pdf',
    'amazon-cloudwatch-monitoring.pdf': 'https://docs.aws.amazon.com/pdfs/AmazonCloudWatch/latest/monitoring/acw-ug.pdf',
    'amazon-cloudwatch-logs.pdf': 'https://docs.aws.amazon.com/pdfs/AmazonCloudWatch/latest/logs/cwl-ug.pdf',
    'amazon-eventbridge.pdf': 'https://docs.aws.amazon.com/pdfs/eventbridge/latest/userguide/user-guide.pdf',
    'aws-config.pdf': 'https://docs.aws.amazon.com/pdfs/config/latest/developerguide/config-dg.pdf',
    'aws-control-tower.pdf': 'https://docs.aws.amazon.com/pdfs/controltower/latest/userguide/controltower-ug.pdf',
    'amazon-managed-grafana.pdf': 'https://docs.aws.amazon.com/pdfs/grafana/latest/userguide/service-guide.pdf.pdf',
    'aws-organizations.pdf': 'https://docs.aws.amazon.com/pdfs/organizations/latest/userguide/organizations-userguide.pdf',
    'aws-resilience-hub.pdf': 'https://docs.aws.amazon.com/pdfs/resilience-hub/latest/userguide/resilience-hub-guide.pdf',
    'aws-resource-explorer.pdf': 'https://docs.aws.amazon.com/pdfs/resource-explorer/latest/userguide/resource_explorer_ug.pdf',
    'aws-service-catalog.pdf': 'https://docs.aws.amazon.com/pdfs/servicecatalog/latest/adminguide/service-catalog-ag.pdf',
    'aws-systems-manager.pdf': 'https://docs.aws.amazon.com/pdfs/systems-manager/latest/userguide/systems-manager-ug.pdf',
    'aws-trusted-advisor.pdf': 'https://docs.aws.amazon.com/pdfs/awssupport/latest/user/support-ug.pdf',
    'aws-user-notifications.pdf': 'https://docs.aws.amazon.com/pdfs/notifications/latest/userguide/notifications-guide.pdf.pdf',
    'aws-well-architected-tool.pdf': 'https://docs.aws.amazon.com/pdfs/wellarchitected/latest/userguide/wellarchitected-ug.pdf',
    'amazon-application-recovery-controller.pdf': 'https://docs.aws.amazon.com/pdfs/r53recovery/latest/dg/r53-recovery-guide.pdf.pdf',
    'amazon-vpc.pdf': 'https://docs.aws.amazon.com/pdfs/vpc/latest/userguide/vpc-ug.pdf',
    'aws-site-to-site-vpn.pdf': 'https://docs.aws.amazon.com/pdfs/vpn/latest/s2svpn/s2s-vpn-user-guide.pdf',
    'aws-verified-access.pdf': 'https://docs.aws.amazon.com/pdfs/verified-access/latest/ug/verified-access-ug.pdf',
    'aws-client-vpn.pdf': 'https://docs.aws.amazon.com/pdfs/vpn/latest/clientvpn-user/client-vpn-user-guide.pdf',
    'amazon-cloudfront.pdf': 'https://docs.aws.amazon.com/pdfs/AmazonCloudFront/latest/DeveloperGuide/AmazonCloudFront_DevGuide.pdf',
    'amazon-verified-permissions.pdf': 'https://docs.aws.amazon.com/pdfs/verifiedpermissions/latest/userguide/amazon-verified-permissions-user-guide.pdf',
    'amazon-route-53.pdf': 'https://docs.aws.amazon.com/pdfs/Route53/latest/DeveloperGuide/route53-dg.pdf',
    'aws-direct-connect.pdf': 'https://docs.aws.amazon.com/pdfs/directconnect/latest/UserGuide/dc-ug.pdf',
    'elastic-load-balancing.pdf': 'https://docs.aws.amazon.com/pdfs/elasticloadbalancing/latest/userguide/elb-ug.pdf',
    'aws-transit-gateway.pdf': 'https://docs.aws.amazon.com/pdfs/vpc/latest/tgw/vpc-tgw.pdf',
    'aws-artifact.pdf': 'https://docs.aws.amazon.com/pdfs/artifact/latest/ug/artifact-ug.pdf',
    'aws-audit-manager.pdf': 'https://docs.aws.amazon.com/pdfs/audit-manager/latest/userguide/audit-manager-ug.pdf',
    'aws-certificate-manager.pdf': 'https://docs.aws.amazon.com/pdfs/acm/latest/userguide/acm-ug.pdf',
    'aws-cloudhsm.pdf': 'https://docs.aws.amazon.com/pdfs/cloudhsm/latest/userguide/cloudhsm-user-guide.pdf',
    'amazon-cognito.pdf': 'https://docs.aws.amazon.com/pdfs/cognito/latest/developerguide/cognito-dg.pdf',
    'amazon-detective.pdf': 'https://docs.aws.amazon.com/pdfs/detective/latest/userguide/detective-ug.pdf',
    'aws-directory-service.pdf': 'https://docs.aws.amazon.com/pdfs/directoryservice/latest/admin-guide/directoryservice-admin-guide.pdf',
    'aws-firewall-manager.pdf': 'https://docs.aws.amazon.com/pdfs/waf/latest/developerguide/waf-dg.pdf',
    'amazon-guardduty.pdf': 'https://docs.aws.amazon.com/pdfs/guardduty/latest/ug/guardduty-ug.pdf',
    'aws-identity-and-access-management.pdf': 'https://docs.aws.amazon.com/pdfs/IAM/latest/UserGuide/iam-ug.pdf',
    'aws-iam-identity-center.pdf': 'https://docs.aws.amazon.com/pdfs/singlesignon/latest/userguide/sso-ug.pdf',
    'amazon-inspector.pdf': 'https://docs.aws.amazon.com/pdfs/inspector/latest/user/inspector-guide.pdf',
    'aws-key-management-service.pdf': 'https://docs.aws.amazon.com/pdfs/kms/latest/developerguide/kms-dg.pdf',
    'amazon-macie.pdf': 'https://docs.aws.amazon.com/pdfs/macie/latest/user/macie-user-guide.pdf',
    'aws-network-firewall.pdf': 'https://docs.aws.amazon.com/pdfs/network-firewall/latest/developerguide/network-firewall-developer-guide.pdf',
    'aws-private-certificate-authority.pdf': 'https://docs.aws.amazon.com/pdfs/privateca/latest/userguide/privateca-ug.pdf',
    'aws-secrets-manager.pdf': 'https://docs.aws.amazon.com/pdfs/secretsmanager/latest/userguide/secretsmanager-userguide.pdf',
    'aws-security-hub.pdf': 'https://docs.aws.amazon.com/pdfs/securityhub/latest/userguide/securityhub.pdf',
    'amazon-security-lake.pdf': 'https://docs.aws.amazon.com/pdfs/security-lake/latest/userguide/security-lake-userguide.pdf',
    'amazon-s3.pdf': 'https://docs.aws.amazon.com/pdfs/AmazonS3/latest/userguide/s3-userguide.pdf',
    'aws-backup.pdf': 'https://docs.aws.amazon.com/pdfs/aws-backup/latest/devguide/AWSBackup-dg.pdf',
    'aws-datasync.pdf': 'https://docs.aws.amazon.com/pdfs/datasync/latest/userguide/datasync-userguide.pdf',
    'amazon-efs.pdf': 'https://docs.aws.amazon.com/pdfs/efs/latest/ug/efs-ug.pdf',
    'amazon-fsx-for-lustre.pdf': 'https://docs.aws.amazon.com/pdfs/fsx/latest/FileCacheGuide/FileCacheGuide.pdf'
}

def handler(event, context):

    s3 = boto3.client('s3')
    bucket = os.environ['S3_BUCKET']

    downloaded = []
    failed = []

    for key, pdf in pdfs.items():

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
