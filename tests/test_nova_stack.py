import tempfile
import json
import unittest

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from scs.scs_stack import ScsStack


class NovaStackTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        app = cdk.App(outdir = cls.directory.name)
        stack = ScsStack(app, 'TestStack', env = cdk.Environment(
            account = '123456789012', region = 'us-east-2'
        ))
        cls.template = Template.from_stack(stack)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_unversioned_private_buckets_are_retained(self):
        for name in ('read-use2-lukach-io', 'nova-use2-lukach-io', 'flex-use2-lukach-io',
                     'batch-use2-lukach-io'):
            self.template.has_resource('AWS::S3::Bucket', {
                'DeletionPolicy': 'Retain',
                'Properties': Match.object_like({
                    'BucketName': name,
                    'VersioningConfiguration': Match.absent(),
                    'PublicAccessBlockConfiguration': {
                        'BlockPublicAcls': True, 'BlockPublicPolicy': True,
                        'IgnorePublicAcls': True, 'RestrictPublicBuckets': True
                    },
                    'BucketEncryption': Match.any_value()
                })
            })

    def test_queue_visibility_retry_policy_and_retention(self):
        self.template.has_resource_properties('AWS::SQS::Queue', {
            'QueueName': 'read2nova',
            'VisibilityTimeout': 5400,
            'MessageRetentionPeriod': 1209600,
            'SqsManagedSseEnabled': True,
            'RedrivePolicy': {
                'deadLetterTargetArn': Match.any_value(), 'maxReceiveCount': 5
            }
        })
        self.template.has_resource_properties('AWS::SQS::Queue', {
            'QueueName': 'read2nova-dlq',
            'MessageRetentionPeriod': 1209600,
            'SqsManagedSseEnabled': True
        })

    def test_single_worker_and_partial_batch_failures(self):
        self.template.has_resource_properties('AWS::Lambda::Function', {
            'FunctionName': 'read2nova', 'Runtime': 'python3.13',
            'Architectures': ['arm64'], 'Handler': 'read2nova.handler',
            'Timeout': 900, 'ReservedConcurrentExecutions': 1,
            'Environment': {'Variables': Match.object_like({
                'MODEL_ID': 'us.amazon.nova-2-lite-v1:0',
                'FLEX_BUCKET': Match.any_value(),
                'REQUESTS_PER_MINUTE': {'Ref': 'NovaRequestsPerMinute'},
                'TOKENS_PER_MINUTE': {'Ref': 'NovaTokensPerMinute'},
                'BATCH_SIZE': {'Ref': 'NovaBatchSize'},
                'MAX_ACTIVE_JOBS': {'Ref': 'NovaActiveJobs'}
            })}
        })
        self.template.has_resource_properties('AWS::Lambda::EventSourceMapping', {
            'BatchSize': 10,
            'FunctionResponseTypes': ['ReportBatchItemFailures']
        })
        functions = self.template.find_resources('AWS::Lambda::Function')
        worker = next(resource['Properties'] for resource in functions.values()
                      if resource['Properties'].get('FunctionName') == 'read2nova')
        self.assertNotEqual(worker.get('PackageType'), 'Image')
        self.assertIn('S3Key', worker['Code'])

    def test_s3_object_created_notifications_use_sqs(self):
        self.template.has_resource_properties('Custom::S3BucketNotifications', {
            'NotificationConfiguration': {
                'QueueConfigurations': [{
                    'Events': ['s3:ObjectCreated:*'],
                    'QueueArn': Match.any_value(),
                    'Filter': {'Key': {'FilterRules': [{'Name': 'suffix', 'Value': '.md'}]}}
                }]
            }
        })

    def test_chunk2read_is_zip_based_and_manual_only(self):
        functions = self.template.find_resources('AWS::Lambda::Function')
        identifier, resource = next(
            (name, resource) for name, resource in functions.items()
            if resource['Properties'].get('FunctionName') == 'chunk2read'
        )
        worker = resource['Properties']
        self.assertEqual(worker['Runtime'], 'python3.13')
        self.assertEqual(worker['Architectures'], ['arm64'])
        self.assertEqual(worker['Handler'], 'chunk2read.handler')
        self.assertEqual(worker['Timeout'], 900)
        self.assertEqual(worker['ReservedConcurrentExecutions'], 1)
        self.assertNotEqual(worker.get('PackageType'), 'Image')
        self.assertIn('S3Key', worker['Code'])
        self.assertEqual(set(worker['Environment']['Variables']), {
            'CHUNK_BUCKET', 'NOVA_BUCKET', 'READ_BUCKET', 'FLEX_BUCKET'
        })
        for kind in ('AWS::Lambda::EventSourceMapping', 'AWS::Events::Rule',
                     'AWS::Lambda::Permission', 'Custom::S3BucketNotifications'):
            self.assertNotIn(identifier, json.dumps(self.template.find_resources(kind)))
        policies = self.template.find_resources('AWS::IAM::Policy')
        policy = next(policy for policy in policies.values()
                      if {'Ref': worker['Role']['Fn::GetAtt'][0]} in policy['Properties']['Roles'])
        statements = policy['Properties']['PolicyDocument']['Statement']
        buckets = {
            bucket['Properties']['BucketName']: name
            for name, bucket in self.template.find_resources('AWS::S3::Bucket').items()
        }
        for name, action in (
            ('chunk-use2-lukach-io', 's3:GetObject*'),
            ('nova-use2-lukach-io', 's3:ListBucket'),
            ('read-use2-lukach-io', 's3:PutObject'),
            ('flex-use2-lukach-io', 's3:PutObject')
        ):
            self.assertTrue(any(
                action in statement['Action']
                and buckets[name] in json.dumps(statement['Resource'])
                for statement in statements
            ))
        self.template.has_resource_properties('AWS::Logs::LogGroup', {
            'LogGroupName': {'Fn::Join': ['', ['/aws/lambda/', {'Ref': identifier}]]},
            'RetentionInDays': 30
        })

    def test_batch_and_flex_defaults(self):
        template = self.template.to_json()
        self.assertEqual(template['Parameters']['NovaBatchSize']['Default'], 500)
        self.assertEqual(template['Parameters']['NovaBatchSize']['MinValue'], 100)
        self.assertEqual(template['Parameters']['NovaActiveJobs']['Default'], 2)
        self.assertEqual(template['Parameters']['NovaMaxOutputTokens']['Default'], 8000)
        for name in ('ChunkFailures', 'LowCondensation'):
            self.template.has_resource_properties('AWS::Logs::MetricFilter', {
                'MetricTransformations': [Match.object_like({
                    'MetricNamespace': 'Read2Nova', 'MetricName': name
                })]
            })
        self.template.has_resource_properties('AWS::DynamoDB::Table', {
            'BillingMode': 'PAY_PER_REQUEST',
            'TableName': 'read2nova-state',
            'KeySchema': [{'AttributeName': 'id', 'KeyType': 'HASH'}],
            'GlobalSecondaryIndexes': [Match.object_like({
                'IndexName': 'by-status',
                'Projection': {'ProjectionType': 'KEYS_ONLY'}
            })]
        })

    def test_model_permissions_cover_profile_and_cross_region_model(self):
        policies = self.template.find_resources('AWS::IAM::Policy')
        statements = [
            statement
            for policy in policies.values()
            for statement in policy['Properties']['PolicyDocument']['Statement']
            if statement.get('Action') == 'bedrock:InvokeModel'
        ]
        self.assertEqual(len(statements), 2)
        self.assertEqual(statements[0]['Effect'], 'Allow')
        resources = statements[0]['Resource']
        self.assertEqual(len(resources), 2)
        self.assertIn(
            ':bedrock:us-east-2:123456789012:inference-profile/us.amazon.nova-2-lite-v1:0',
            json.dumps(resources[0])
        )
        self.assertIn(
            ':bedrock:*::foundation-model/amazon.nova-2-lite-v1:0',
            json.dumps(resources[1])
        )

    def test_schedule_job_events_and_workflow_failure_destination(self):
        self.template.has_resource_properties('AWS::Events::Rule', {
            'ScheduleExpression': 'rate(5 minutes)'
        })
        self.template.has_resource_properties('AWS::Events::Rule', {
            'EventPattern': {
                'source': ['aws.bedrock'],
                'detail-type': ['Batch Inference Job State Change'],
                'detail': {
                    'batchJobName': [{'prefix': 'read2nova-'}],
                    'status': ['Completed', 'PartiallyCompleted', 'Failed', 'Expired', 'Stopped']
                }
            }
        })
        self.template.has_resource_properties('AWS::Lambda::EventInvokeConfig', {
            'MaximumRetryAttempts': 0,
            'DestinationConfig': {'OnFailure': {'Destination': Match.any_value()}}
        })
        self.template.resource_count_is('AWS::CloudWatch::Alarm', 6)

    def test_flex_notifications_have_separate_queue_and_dlq(self):
        self.template.has_resource_properties('AWS::SQS::Queue', {
            'QueueName': 'flex2nova',
            'VisibilityTimeout': 5400,
            'MessageRetentionPeriod': 1209600,
            'SqsManagedSseEnabled': True,
            'RedrivePolicy': {
                'deadLetterTargetArn': Match.any_value(), 'maxReceiveCount': 5
            }
        })
        self.template.has_resource_properties('AWS::SQS::Queue', {
            'QueueName': 'flex2nova-dlq',
            'MessageRetentionPeriod': 1209600, 'SqsManagedSseEnabled': True
        })
        self.template.has_resource_properties('AWS::Lambda::EventSourceMapping', {
            'BatchSize': 1, 'FunctionResponseTypes': ['ReportBatchItemFailures']
        })
        resources = self.template.to_json()['Resources']
        buckets = {
            resource['Properties']['BucketName']: identifier
            for identifier, resource in resources.items()
            if resource['Type'] == 'AWS::S3::Bucket'
        }
        queues = {
            resource['Properties']['QueueName']: identifier
            for identifier, resource in resources.items()
            if resource['Type'] == 'AWS::SQS::Queue'
        }
        for bucket_name, queue_name in (
            ('read-use2-lukach-io', 'read2nova'),
            ('flex-use2-lukach-io', 'flex2nova')
        ):
            notification = next(
                resource['Properties']
                for resource in resources.values()
                if resource['Type'] == 'Custom::S3BucketNotifications'
                and resource['Properties']['BucketName'] == {'Ref': buckets[bucket_name]}
            )
            self.assertEqual(
                notification['NotificationConfiguration']['QueueConfigurations'][0]['QueueArn'],
                {'Fn::GetAtt': [queues[queue_name], 'Arn']}
            )

    def test_batch_role_is_scoped_to_account_and_job_arns(self):
        self.template.has_resource_properties('AWS::IAM::Role', {
            'AssumeRolePolicyDocument': {
                'Statement': [Match.object_like({
                    'Principal': {'Service': 'bedrock.amazonaws.com'},
                    'Condition': {
                        'StringEquals': {'aws:SourceAccount': '123456789012'},
                        'ArnLike': {'aws:SourceArn': Match.any_value()}
                    }
                })],
                'Version': '2012-10-17'
            }
        })
        policies = self.template.find_resources('AWS::IAM::Policy')
        statements = [statement for policy in policies.values()
                      for statement in policy['Properties']['PolicyDocument']['Statement']]
        actions = [statement['Action'] for statement in statements]
        self.assertIn('bedrock:CreateModelInvocationJob', actions)
        self.assertIn('bedrock:GetModelInvocationJob', actions)
        pass_role = next(statement for statement in statements if statement['Action'] == 'iam:PassRole')
        self.assertEqual(pass_role['Condition'],
                         {'StringEquals': {'iam:PassedToService': 'bedrock.amazonaws.com'}})
        roles = self.template.find_resources('AWS::IAM::Role')
        batch_role = next(name for name, role in roles.items()
                          if 'Condition' in role['Properties']['AssumeRolePolicyDocument']['Statement'][0])
        buckets = {bucket['Properties'].get('BucketName'): name
                   for name, bucket in self.template.find_resources('AWS::S3::Bucket').items()}
        role_policies = json.dumps([policy for policy in policies.values()
                                    if {'Ref': batch_role} in policy['Properties']['Roles']])
        self.assertIn(buckets['batch-use2-lukach-io'], role_policies)
        for name in ('read-use2-lukach-io', 'flex-use2-lukach-io', 'nova-use2-lukach-io'):
            self.assertNotIn(buckets[name], role_policies)


if __name__ == '__main__':
    unittest.main()
