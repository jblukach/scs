import datetime

from aws_cdk import (
    CfnParameter,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudwatch as _cloudwatch,
    aws_ecr_assets as _ecr_assets,
    aws_dynamodb as _dynamodb,
    aws_events as _events,
    aws_events_targets as _targets,
    aws_iam as _iam,
    aws_lambda as _lambda,
    aws_lambda_event_sources as _sources,
    aws_lambda_destinations as _destinations,
    aws_logs as _logs,
    aws_s3 as _s3,
    aws_s3_notifications as _s3n,
    aws_sqs as _sqs
)

from constructs import Construct

class ScsStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

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

        raw_bucket = _s3.Bucket(
            self, 'raw_bucket',
            bucket_name = 'raw-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.DESTROY,
            auto_delete_objects = True
        )

        split_bucket = _s3.Bucket(
            self, 'split_bucket',
            bucket_name = 'split-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.DESTROY,
            auto_delete_objects = True
        )

        chunk_bucket = _s3.Bucket(
            self, 'chunk_bucket',
            bucket_name = 'chunk-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.DESTROY,
            auto_delete_objects = True
        )

        read_bucket = _s3.Bucket(
            self, 'read_bucket',
            bucket_name = 'read-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.RETAIN
        )

        nova_bucket = _s3.Bucket(
            self, 'nova_bucket',
            bucket_name = 'nova-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.RETAIN
        )

        flex_bucket = _s3.Bucket(
            self, 'flex_bucket',
            bucket_name = 'flex-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.RETAIN
        )

        batch_bucket = _s3.Bucket(
            self, 'batch_bucket',
            bucket_name = 'batch-use2-lukach-io',
            encryption = _s3.BucketEncryption.S3_MANAGED,
            block_public_access = _s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl = True,
            removal_policy = RemovalPolicy.RETAIN
        )

    ### LAMBDA LAYER ###

        requests = _lambda.LayerVersion(
            self, 'requests',
            layer_version_name = 'requests',
            description = datetime.date.today().isoformat()+' deployment',
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

        _logs.LogGroup(
            self, 'logs',
            log_group_name = '/aws/lambda/'+download.function_name,
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
            memory_size = 4096
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

        raw2split = _lambda.DockerImageFunction(
            self, 'raw2split',
            function_name = 'raw2split',
            code = _lambda.DockerImageCode.from_image_asset(
                'raw2split',
                platform = _ecr_assets.Platform.LINUX_AMD64
            ),
            architecture = _lambda.Architecture.X86_64,
            environment = dict(
                SPLIT_BUCKET = split_bucket.bucket_name
            ),
            timeout = Duration.seconds(900),
            memory_size = 4096
        )

        raw_bucket.grant_read(raw2split)
        split_bucket.grant_put(raw2split)
        raw_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED,
            _s3n.LambdaDestination(raw2split)
        )

        _logs.LogGroup(
            self, 'raw2split_logs',
            log_group_name = '/aws/lambda/'+raw2split.function_name,
            retention = _logs.RetentionDays.ONE_MONTH,
            removal_policy = RemovalPolicy.DESTROY
        )

        text2chunk = _lambda.Function(
            self, 'text2chunk',
            function_name = 'text2chunk',
            runtime = _lambda.Runtime.PYTHON_3_13,
            architecture = _lambda.Architecture.ARM_64,
            code = _lambda.Code.from_asset('text2chunk'),
            handler = 'text2chunk.handler',
            environment = dict(
                MD_BUCKET = md_bucket.bucket_name,
                CHUNK_BUCKET = chunk_bucket.bucket_name
            ),
            timeout = Duration.seconds(900),
            memory_size = 3008
        )

        md_bucket.grant_read(text2chunk)
        chunk_bucket.grant_put(text2chunk)

        _logs.LogGroup(
            self, 'text2chunk_logs',
            log_group_name = '/aws/lambda/'+text2chunk.function_name,
            retention = _logs.RetentionDays.ONE_MONTH,
            removal_policy = RemovalPolicy.DESTROY
        )

        chunk2read = _lambda.Function(
            self, 'chunk2read',
            function_name = 'chunk2read',
            runtime = _lambda.Runtime.PYTHON_3_13,
            architecture = _lambda.Architecture.ARM_64,
            code = _lambda.Code.from_asset(
                'chunk2read', exclude = ['__pycache__', '*.pyc']
            ),
            handler = 'chunk2read.handler',
            environment = dict(
                CHUNK_BUCKET = chunk_bucket.bucket_name,
                NOVA_BUCKET = nova_bucket.bucket_name,
                READ_BUCKET = read_bucket.bucket_name,
                FLEX_BUCKET = flex_bucket.bucket_name
            ),
            timeout = Duration.seconds(900),
            memory_size = 1024,
            reserved_concurrent_executions = 1
        )

        chunk_bucket.grant_read(chunk2read)
        chunk2read.add_to_role_policy(_iam.PolicyStatement(
            actions = ['s3:ListBucket'],
            resources = [nova_bucket.bucket_arn]
        ))
        read_bucket.grant_put(chunk2read)
        flex_bucket.grant_put(chunk2read)

        _logs.LogGroup(
            self, 'chunk2read_logs',
            log_group_name = '/aws/lambda/'+chunk2read.function_name,
            retention = _logs.RetentionDays.ONE_MONTH,
            removal_policy = RemovalPolicy.DESTROY
        )

    ### NOVA BATCH PIPELINE ###

        requests_per_minute = CfnParameter(
            self, 'NovaRequestsPerMinute',
            type = 'Number', default = 10, min_value = 1, max_value = 10000,
            description = 'Whole requests/minute budget for automatic FLEX bucket processing'
        )
        tokens_per_minute = CfnParameter(
            self, 'NovaTokensPerMinute',
            type = 'Number', default = 100000, min_value = 1,
            description = 'Whole tokens/minute budget for automatic FLEX bucket processing'
        )
        max_output_tokens = CfnParameter(
            self, 'NovaMaxOutputTokens',
            type = 'Number', default = 8000, min_value = 1, max_value = 64000,
            description = 'Maximum output tokens reserved for each edit'
        )
        batch_size = CfnParameter(
            self, 'NovaBatchSize',
            type = 'Number', default = 500, min_value = 100, max_value = 500,
            description = 'Maximum records per asynchronous Nova batch job'
        )
        active_jobs = CfnParameter(
            self, 'NovaActiveJobs',
            type = 'Number', default = 2, min_value = 1, max_value = 10,
            description = 'Batch jobs allocated to this pipeline; leave room for other callers'
        )

        nova_dlq = _sqs.Queue(
            self, 'nova_dlq',
            queue_name = 'read2nova-dlq',
            encryption = _sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl = True,
            retention_period = Duration.days(14),
            removal_policy = RemovalPolicy.RETAIN
        )
        nova_queue = _sqs.Queue(
            self, 'nova_queue',
            queue_name = 'read2nova',
            encryption = _sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl = True,
            retention_period = Duration.days(14),
            visibility_timeout = Duration.seconds(5400),
            dead_letter_queue = _sqs.DeadLetterQueue(
                queue = nova_dlq, max_receive_count = 5
            ),
            removal_policy = RemovalPolicy.RETAIN
        )
        flex_dlq = _sqs.Queue(
            self, 'flex_dlq',
            queue_name = 'flex2nova-dlq',
            encryption = _sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl = True,
            retention_period = Duration.days(14),
            removal_policy = RemovalPolicy.RETAIN
        )
        flex_queue = _sqs.Queue(
            self, 'flex_queue',
            queue_name = 'flex2nova',
            encryption = _sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl = True,
            retention_period = Duration.days(14),
            visibility_timeout = Duration.seconds(5400),
            dead_letter_queue = _sqs.DeadLetterQueue(
                queue = flex_dlq, max_receive_count = 5
            ),
            removal_policy = RemovalPolicy.RETAIN
        )
        quota_table = _dynamodb.Table(
            self, 'nova_quota',
            table_name = 'read2nova-state',
            partition_key = _dynamodb.Attribute(
                name = 'id', type = _dynamodb.AttributeType.STRING
            ),
            billing_mode = _dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy = RemovalPolicy.RETAIN
        )
        quota_table.add_global_secondary_index(
            index_name = 'by-status',
            partition_key = _dynamodb.Attribute(
                name = 'status', type = _dynamodb.AttributeType.STRING
            ),
            sort_key = _dynamodb.Attribute(
                name = 'created', type = _dynamodb.AttributeType.STRING
            ),
            projection_type = _dynamodb.ProjectionType.KEYS_ONLY
        )
        model_resources = [
            self.format_arn(
                service = 'bedrock', resource = 'inference-profile',
                resource_name = 'us.amazon.nova-2-lite-v1:0'
            ),
            self.format_arn(
                service = 'bedrock', region = '*', account = '',
                resource = 'foundation-model',
                resource_name = 'amazon.nova-2-lite-v1:0'
            )
        ]
        job_resources = [self.format_arn(
            service = 'bedrock', resource = 'model-invocation-job', resource_name = '*'
        )]
        batch_role = _iam.Role(
            self, 'nova_batch_role',
            assumed_by = _iam.ServicePrincipal(
                'bedrock.amazonaws.com',
                conditions = {
                    'StringEquals': {'aws:SourceAccount': self.account},
                    'ArnLike': {'aws:SourceArn': job_resources[0]}
                }
            )
        )
        batch_bucket.grant_read(batch_role, 'jobs/*')
        batch_bucket.grant_put(batch_role, 'jobs/*')
        batch_role.add_to_policy(_iam.PolicyStatement(
            actions = ['bedrock:InvokeModel'], resources = model_resources
        ))

        read2nova = _lambda.Function(
            self, 'read2nova',
            function_name = 'read2nova',
            runtime = _lambda.Runtime.PYTHON_3_13,
            architecture = _lambda.Architecture.ARM_64,
            code = _lambda.Code.from_asset(
                'read2nova', exclude = ['__pycache__', '*.pyc']
            ),
            handler = 'read2nova.handler',
            environment = dict(
                READ_BUCKET = read_bucket.bucket_name,
                BATCH_BUCKET = batch_bucket.bucket_name,
                FLEX_BUCKET = flex_bucket.bucket_name,
                NOVA_BUCKET = nova_bucket.bucket_name,
                MODEL_ID = 'us.amazon.nova-2-lite-v1:0',
                STATE_TABLE = quota_table.table_name,
                BATCH_ROLE_ARN = batch_role.role_arn,
                BATCH_SIZE = batch_size.value_as_string,
                MAX_ACTIVE_JOBS = active_jobs.value_as_string,
                REQUESTS_PER_MINUTE = requests_per_minute.value_as_string,
                TOKENS_PER_MINUTE = tokens_per_minute.value_as_string,
                MAX_OUTPUT_TOKENS = max_output_tokens.value_as_string
            ),
            timeout = Duration.seconds(900),
            memory_size = 1024,
            reserved_concurrent_executions = 1
        )
        read_bucket.grant_read(read2nova)
        flex_bucket.grant_read(read2nova)
        batch_bucket.grant_read(read2nova)
        batch_bucket.grant_put(read2nova)
        nova_bucket.grant_read(read2nova)
        nova_bucket.grant_put(read2nova)
        quota_table.grant_read_write_data(read2nova)
        read2nova.add_to_role_policy(_iam.PolicyStatement(
            actions = ['bedrock:InvokeModel'],
            resources = model_resources
        ))
        read2nova.add_to_role_policy(_iam.PolicyStatement(
            actions = ['bedrock:CreateModelInvocationJob'],
            resources = job_resources + model_resources
        ))
        read2nova.add_to_role_policy(_iam.PolicyStatement(
            actions = ['bedrock:GetModelInvocationJob'], resources = job_resources
        ))
        read2nova.add_to_role_policy(_iam.PolicyStatement(
            actions = ['iam:PassRole'], resources = [batch_role.role_arn],
            conditions = {'StringEquals': {'iam:PassedToService': 'bedrock.amazonaws.com'}}
        ))
        read2nova.add_event_source(_sources.SqsEventSource(
            nova_queue,
            batch_size = 10,
            report_batch_item_failures = True
        ))
        read_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED,
            _s3n.SqsDestination(nova_queue),
            _s3.NotificationKeyFilter(suffix = '.md')
        )
        read2nova.add_event_source(_sources.SqsEventSource(
            flex_queue,
            batch_size = 1,
            report_batch_item_failures = True
        ))
        flex_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED,
            _s3n.SqsDestination(flex_queue),
            _s3.NotificationKeyFilter(suffix = '.md')
        )
        nova_logs = _logs.LogGroup(
            self, 'read2nova_logs',
            log_group_name = '/aws/lambda/'+read2nova.function_name,
            retention = _logs.RetentionDays.ONE_MONTH,
            removal_policy = RemovalPolicy.DESTROY
        )
        workflow_dlq = _sqs.Queue(
            self, 'nova_workflow_dlq',
            queue_name = 'read2nova-workflow-dlq',
            encryption = _sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl = True,
            retention_period = Duration.days(14),
            removal_policy = RemovalPolicy.RETAIN
        )
        read2nova.configure_async_invoke(
            retry_attempts = 0,
            max_event_age = Duration.hours(1),
            on_failure = _destinations.SqsDestination(workflow_dlq)
        )
        target = _targets.LambdaFunction(
            read2nova,
            event = _events.RuleTargetInput.from_object({'action': 'dispatch'}),
            dead_letter_queue = workflow_dlq
        )
        _events.Rule(
            self, 'nova_dispatch_schedule',
            schedule = _events.Schedule.rate(Duration.minutes(5)),
            targets = [target]
        )
        _events.Rule(
            self, 'nova_job_events',
            event_pattern = _events.EventPattern(
                source = ['aws.bedrock'],
                detail_type = ['Batch Inference Job State Change'],
                detail = {
                    'batchJobName': [{'prefix': 'read2nova-'}],
                    'status': ['Completed', 'PartiallyCompleted', 'Failed', 'Expired', 'Stopped']
                }
            ),
            targets = [target]
        )
        for identifier, metric in (
            ('nova_ingestion_dlq_alarm', nova_dlq.metric_approximate_number_of_messages_visible()),
            ('nova_flex_dlq_alarm', flex_dlq.metric_approximate_number_of_messages_visible()),
            ('nova_flex_queue_age_alarm', flex_queue.metric_approximate_age_of_oldest_message()),
            ('nova_workflow_dlq_alarm', workflow_dlq.metric_approximate_number_of_messages_visible()),
            ('nova_queue_age_alarm', nova_queue.metric_approximate_age_of_oldest_message())
        ):
            _cloudwatch.Alarm(
                self, identifier, metric = metric,
                threshold = 86400 if identifier.endswith('queue_age_alarm') else 1,
                evaluation_periods = 1,
                treat_missing_data = _cloudwatch.TreatMissingData.NOT_BREACHING
            )
        _logs.MetricFilter(
            self, 'nova_chunk_failures',
            log_group = nova_logs,
            filter_pattern = _logs.FilterPattern.literal('"ChunkFailed"'),
            metric_namespace = 'Read2Nova', metric_name = 'ChunkFailures',
            metric_value = '1'
        )
        _cloudwatch.Alarm(
            self, 'nova_chunk_failure_alarm',
            metric = _cloudwatch.Metric(
                namespace = 'Read2Nova', metric_name = 'ChunkFailures',
                statistic = 'Sum', period = Duration.minutes(5)
            ),
            threshold = 1, evaluation_periods = 1,
            treat_missing_data = _cloudwatch.TreatMissingData.NOT_BREACHING
        )
        _logs.MetricFilter(
            self, 'nova_low_condensation',
            log_group = nova_logs,
            filter_pattern = _logs.FilterPattern.literal('"LowCondensation"'),
            metric_namespace = 'Read2Nova', metric_name = 'LowCondensation',
            metric_value = '1'
        )
