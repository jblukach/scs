import datetime

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Size,
    Stack,
    aws_ecr_assets as _ecr_assets,
    aws_iam as _iam,
    aws_lambda as _lambda,
    aws_logs as _logs,
    aws_s3 as _s3,
    aws_s3_notifications as _s3n
)

from constructs import Construct

class ScsStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        now = datetime.datetime.now()
        year = now.year
        month = now.strftime('%m')
        day = now.strftime('%d')

    ### S3 BUCKETS ###

        packages = _s3.Bucket.from_bucket_name(
            self, 'packages',
            bucket_name = 'packages-use2-lukach-io'
        )

        bucket = _s3.Bucket(
            self, 'bucket',
            bucket_name = 'scs-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.DESTROY,
            auto_delete_objects = True
        )

        pdf_bucket = _s3.Bucket(
            self, 'pdf_bucket',
            bucket_name = 'pdf-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.DESTROY,
            auto_delete_objects = True
        )

        md_bucket = _s3.Bucket(
            self, 'md_bucket',
            bucket_name = 'md-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.DESTROY,
            auto_delete_objects = True
        )

    ### LAMBDA LAYER ###

        requests = _lambda.LayerVersion(
            self, 'requests',
            layer_version_name = 'requests',
            description = str(year)+'-'+str(month)+'-'+str(day)+' deployment',
            code = _lambda.Code.from_bucket(
                bucket = packages,
                key = 'requests.zip'
            ),
            compatible_architectures = [
                _lambda.Architecture.ARM_64
            ],
            compatible_runtimes = [
                _lambda.Runtime.PYTHON_3_13
            ],
            removal_policy = RemovalPolicy.DESTROY
        )

    ### IAM ROLE ###

        role = _iam.Role(
            self, 'role',
            assumed_by = _iam.ServicePrincipal(
                'lambda.amazonaws.com'
            )
        )

        role.add_to_policy(
            _iam.PolicyStatement(
                actions = [
                    'logs:CreateLogGroup',
                    'logs:CreateLogStream',
                    'logs:PutLogEvents'
                ],
                resources = [
                    '*'
                ]
            )
        )

        bucket.grant_put(role)

    ### LAMBDA FUNCTION ###

        download = _lambda.Function(
            self, 'download',
            function_name = 'scs-download',
            runtime = _lambda.Runtime.PYTHON_3_13,
            architecture = _lambda.Architecture.ARM_64,
            code = _lambda.Code.from_asset('download'),
            handler = 'download.handler',
            environment = dict(
                S3_BUCKET = bucket.bucket_name
            ),
            timeout = Duration.seconds(900),
            memory_size = 1024,
            role = role,
            layers = [
                requests
            ]
        )

        logs = _logs.LogGroup(
            self, 'logs',
            log_group_name = '/aws/lambda/'+download.function_name,
            retention = _logs.RetentionDays.ONE_MONTH,
            removal_policy = RemovalPolicy.DESTROY
        )

        copypdfs = _lambda.Function(
            self, 'copypdfs',
            function_name = 'scs-pdf2md',
            runtime = _lambda.Runtime.PYTHON_3_13,
            architecture = _lambda.Architecture.ARM_64,
            code = _lambda.Code.from_asset('copypdfs'),
            handler = 'copypdfs.handler',
            environment = dict(
                SOURCE_BUCKET = bucket.bucket_name,
                DESTINATION_BUCKET = pdf_bucket.bucket_name
            ),
            timeout = Duration.seconds(900),
            memory_size = 1024
        )

        bucket.grant_read(copypdfs)
        pdf_bucket.grant_put(copypdfs)

        _logs.LogGroup(
            self, 'copypdfs_logs',
            log_group_name = '/aws/lambda/'+copypdfs.function_name,
            retention = _logs.RetentionDays.ONE_MONTH,
            removal_policy = RemovalPolicy.DESTROY
        )

        pdf2md = _lambda.DockerImageFunction(
            self, 'pdf2md',
            function_name = 'pdf2md',
            code = _lambda.DockerImageCode.from_image_asset(
                'pdf2md',
                platform = _ecr_assets.Platform.LINUX_AMD64
            ),
            architecture = _lambda.Architecture.X86_64,
            environment = dict(
                MD_BUCKET = md_bucket.bucket_name
            ),
            timeout = Duration.seconds(900),
            memory_size = 2048,
            ephemeral_storage_size = Size.mebibytes(2048)
        )

        pdf_bucket.grant_read(pdf2md)
        md_bucket.grant_put(pdf2md)
        pdf_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED,
            _s3n.LambdaDestination(pdf2md)
        )

        _logs.LogGroup(
            self, 'pdf2md_logs',
            log_group_name = '/aws/lambda/'+pdf2md.function_name,
            retention = _logs.RetentionDays.ONE_MONTH,
            removal_policy = RemovalPolicy.DESTROY
        )
