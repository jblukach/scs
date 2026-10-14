# pylint: disable=protected-access
import copy
import hashlib
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


class Body(io.BytesIO):
    """Mimics botocore StreamingBody, whose context manager yields the raw stream."""

    def __enter__(self):
        return io.BufferedReader(io.BytesIO(self.getvalue()))

    def iter_lines(self):
        return iter(self.getvalue().splitlines())


class Read2NovaTests(unittest.TestCase):

    def setUp(self):
        boto3 = MagicMock()
        self.clients = {name: MagicMock() for name in (
            's3', 'bedrock-runtime', 'bedrock', 'dynamodb'
        )}
        boto3.client.side_effect = lambda name, **kwargs: self.clients[name]
        config = MagicMock()
        self.config = config.Config
        exceptions = MagicMock()

        class ClientError(Exception):
            def __init__(self, response):
                super().__init__(str(response))
                self.response = response

        self.ClientError = ClientError
        exceptions.ClientError = ClientError
        path = Path(__file__).resolve().parents[1] / 'read2nova' / 'read2nova.py'
        spec = importlib.util.spec_from_file_location('read2nova_handler', path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            'boto3': boto3, 'botocore.config': config,
            'botocore.exceptions': exceptions
        }):
            spec.loader.exec_module(self.module)
        self.module.logger.addHandler(logging.NullHandler())
        env = patch.dict(os.environ, {
            'READ_BUCKET': 'read-use2-lukach-io',
            'FLEX_BUCKET': 'flex-use2-lukach-io',
            'NOVA_BUCKET': 'nova-use2-lukach-io',
            'BATCH_BUCKET': 'batch-use2-lukach-io',
            'MODEL_ID': 'us.amazon.nova-2-lite-v1:0',
            'STATE_TABLE': 'state', 'BATCH_ROLE_ARN': 'arn:aws:iam::123456789012:role/batch',
            'REQUESTS_PER_MINUTE': '2', 'TOKENS_PER_MINUTE': '100000',
            'MAX_OUTPUT_TOKENS': '8000', 'BATCH_SIZE': '500', 'MAX_ACTIVE_JOBS': '2'
        })
        env.start()
        self.addCleanup(env.stop)
        self.s3 = self.clients['s3']
        self.runtime = self.clients['bedrock-runtime']
        self.batch = self.clients['bedrock']
        self.ddb = self.clients['dynamodb']
        self.items = {}
        self.objects = {}
        self.metadata = {}
        self.jobs = {}
        self.ddb.get_item.side_effect = lambda **kw: {
            'Item': copy.deepcopy(self.items[kw['Key']['id']['S']])
        } if kw['Key']['id']['S'] in self.items else {}
        self.ddb.put_item.side_effect = self.put_item
        self.ddb.query.side_effect = self.query
        self.s3.get_object.side_effect = self.get_object
        self.s3.put_object.side_effect = self.put_object
        self.s3.head_object.side_effect = self.head_object
        self.s3.get_paginator.return_value.paginate.side_effect = self.pages
        self.batch.create_model_invocation_job.side_effect = self.create_job
        self.batch.get_model_invocation_job.side_effect = lambda **kw: {
            'status': self.jobs[kw['jobIdentifier']]
        }
        self.response = {
            'stopReason': 'end_turn',
            'output': {'message': {'content': [{'text': '### Source\n\nFacts.'}]}},
            'usage': {'inputTokens': 10, 'outputTokens': 10}
        }
        self.runtime.converse.return_value = self.response
        self.context = MagicMock()
        self.context.get_remaining_time_in_millis.return_value = 900000

    def put_item(self, **kwargs):
        item = kwargs['Item']
        self.items[item['id']['S']] = copy.deepcopy(item)
        return {}

    def query(self, **kwargs):
        status = kwargs['ExpressionAttributeValues'][':status']['S']
        return {'Items': [
            {'id': item['id']} for item in self.items.values()
            if item.get('status', {}).get('S') == status
        ][:kwargs['Limit']]}

    def get_object(self, **kwargs):
        body = self.objects[(kwargs['Bucket'], kwargs['Key'])]
        if 'IfMatch' in kwargs and kwargs['IfMatch'] != '"' + hashlib.md5(body).hexdigest() + '"':
            raise self.ClientError({'Error': {'Code': 'PreconditionFailed'}})
        return {'Body': Body(body)}

    def put_object(self, **kwargs):
        key = (kwargs['Bucket'], kwargs['Key'])
        self.objects[key] = kwargs['Body']
        self.metadata[key] = kwargs.get('Metadata', {})
        return {}

    def head_object(self, **kwargs):
        key = (kwargs['Bucket'], kwargs['Key'])
        if key not in self.objects:
            raise self.ClientError({'Error': {'Code': '404'}})
        return {'Metadata': self.metadata.get(key, {})}

    def pages(self, **kwargs):
        return [{'Contents': [
            {'Key': key} for bucket, key in self.objects
            if bucket == kwargs['Bucket'] and key.startswith(kwargs['Prefix'])
        ]}]

    def create_job(self, **kwargs):
        arn = 'arn:aws:bedrock:us-east-2:123456789012:model-invocation-job/' + kwargs['clientRequestToken']
        self.jobs.setdefault(arn, 'InProgress')
        return {'jobArn': arn}

    def ingest(self, key = 'guides/my file+.md', sequencer = '1', body = b'## Source\n\nFacts.',
               bucket = 'read-use2-lukach-io'):
        self.objects[(bucket, key)] = body
        return self.module._ingest({'s3': {
            'bucket': {'name': bucket},
            'object': {'key': key.replace('%', '%25').replace('+', '%2B'),
                       'sequencer': sequencer, 'eTag': hashlib.md5(body).hexdigest()}
        }})

    def notify(self, item):
        return self.module.handler({'Records': [{
            'messageId': 'source-message',
            'body': json.dumps({'Records': [{'s3': {
                'bucket': {'name': item['bucket']},
                'object': {'key': item['key'].replace('%', '%25').replace('+', '%2B'),
                           'sequencer': item['sequencer'], 'eTag': item['etag']}
            }}]})
        }]}, self.context)

    def fill(self, count):
        return [self.ingest(f'guides/chunk-{index}.md') for index in range(count)]

    def dispatch(self):
        return self.module.handler({'action': 'dispatch'}, self.context)

    def active(self):
        return self.module._get('control')['active']

    def output(self, job, records):
        self.objects[('batch-use2-lukach-io', f"jobs/{job['id']}/raw/job/input.jsonl.out")] = (
            b'\n'.join(json.dumps(record).encode() for record in records)
        )
        self.jobs[job['arn']] = 'Completed'

    def test_upload_prepares_input_without_inference(self):
        item = self.ingest()
        self.assertEqual(item['status'], 'PENDING')
        self.s3.get_object.assert_called_once_with(
            Bucket = 'read-use2-lukach-io', Key = 'guides/my file+.md',
            IfMatch = '"' + hashlib.md5(b'## Source\n\nFacts.').hexdigest() + '"'
        )
        prepared = json.loads(self.objects[('batch-use2-lukach-io', item['prepared'])])
        self.assertEqual(prepared['recordId'], item['id'])
        self.assertEqual(item['record_bytes'],
                         len(json.dumps(prepared, ensure_ascii = False).encode()) + 1)
        self.assertEqual(prepared['modelInput']['system'], [{'text': self.module.SYSTEM_PROMPT}])
        self.assertEqual(prepared['modelInput']['inferenceConfig'],
                         {'maxTokens': 8000, 'temperature': 0})
        self.assertEqual(item['source_bytes'], len(b'## Source\n\nFacts.'))
        self.assertNotIn('serviceTier', prepared['modelInput'])
        self.runtime.converse.assert_not_called()
        self.batch.create_model_invocation_job.assert_not_called()

    def test_prompt_defines_structure_and_worked_example(self):
        prompt = self.module.SYSTEM_PROMPT
        sections = ['**Key concepts**', '**Configuration, defaults, and limits**',
                    '**When to use and trade-offs**', '> **Key Takeaway:**']
        for marker in ['Required Output Structure', 'Example source:', 'Example output:'] + sections:
            self.assertIn(marker, prompt)
        example = prompt.split('Example output:\n', 1)[1].split('\n\nTreat the user message', 1)[0]
        self.module.validate_markdown(example)
        positions = [example.index(marker) for marker in ['### '] + sections]
        self.assertEqual(positions, sorted(positions))

    def test_low_condensation_is_logged_for_flex_and_batch(self):
        flex = self.ingest('sample.md', bucket = 'flex-use2-lukach-io', body = b'### Source\n\n' + b'x' * 100)
        self.runtime.converse.return_value['output']['message']['content'][0]['text'] = (
            '### Source\n\n' + 'x' * 90
        )
        with self.assertLogs(self.module.logger, level = 'WARNING') as logs:
            self.notify(flex)
        self.assertIn(f"LowCondensation id={flex['id']} key=sample.md ratio=0.91", logs.output[0])
        self.assertEqual(self.module._get(flex['id'])['status'], 'DONE')

        items = [self.ingest(f'guides/chunk-{index}.md', body = b'### Source\n\n' + b'x' * 100)
                 for index in range(100)]
        self.dispatch()
        response = copy.deepcopy(self.response)
        response['output']['message']['content'][0]['text'] = '### Source\n\nShort.'
        self.output(self.active()[0], [{'recordId': item['id'], 'modelOutput': response}
                                       for item in items])
        with self.assertNoLogs(self.module.logger, level = 'WARNING'):
            self.dispatch()
        self.assertEqual(self.module._get(items[0]['id'])['status'], 'DONE')

    def test_duplicate_notification_does_not_reset_progress(self):
        item = self.ingest()
        item['status'] = 'DONE'
        self.module._put(item)
        self.assertEqual(self.ingest()['status'], 'DONE')
        self.assertEqual(self.s3.get_object.call_count, 1)

    def test_fewer_than_100_chunks_wait_without_calls(self):
        self.fill(99)
        self.assertEqual(self.dispatch()['activeJobs'], 0)
        self.batch.create_model_invocation_job.assert_not_called()
        self.runtime.converse.assert_not_called()

    def test_100_chunks_submit_converse_batch_and_persist_ownership(self):
        items = self.fill(100)
        self.assertEqual(self.dispatch()['activeJobs'], 1)
        request = self.batch.create_model_invocation_job.call_args.kwargs
        self.assertEqual(request['modelInvocationType'], 'Converse')
        self.assertEqual(request['modelId'], 'us.amazon.nova-2-lite-v1:0')
        self.assertEqual(request['roleArn'], os.environ['BATCH_ROLE_ARN'])
        job = self.active()[0]
        self.assertEqual(request['clientRequestToken'], job['id'])
        payload = self.objects[('batch-use2-lukach-io', f"jobs/{job['id']}/input.jsonl")]
        self.assertEqual(len(payload.splitlines()), 100)
        self.assertEqual({json.loads(line)['recordId'] for line in payload.splitlines()},
                         {item['id'] for item in items})
        self.assertTrue(all(self.module._get(item['id'])['status'] == 'BATCH' for item in items))
        self.assertEqual(request['outputDataConfig']['s3OutputDataConfig']['s3Uri'],
                         f"s3://batch-use2-lukach-io/jobs/{job['id']}/raw/")

    def test_nova_bucket_contains_only_edited_markdown(self):
        items = self.fill(100)
        self.dispatch()
        job = self.active()[0]
        self.output(job, [{'recordId': item['id'], 'modelOutput': self.response} for item in items])
        self.dispatch()
        self.assertFalse(self.active())
        for bucket in ('nova-use2-lukach-io', 'read-use2-lukach-io'):
            self.assertEqual(sorted(key for name, key in self.objects if name == bucket),
                             sorted(item['key'] for item in items))
        self.assertIn(('batch-use2-lukach-io', f"jobs/{job['id']}/manifest.json"), self.objects)

    def test_batch_size_and_active_job_limit(self):
        self.fill(1100)
        self.assertEqual(self.dispatch()['activeJobs'], 2)
        self.assertEqual([len(job['ids']) for job in self.active()], [500, 500])
        self.assertEqual(self.dispatch()['activeJobs'], 2)
        self.assertEqual(self.batch.create_model_invocation_job.call_count, 2)

    def test_batch_input_byte_limit_caps_selected_records(self):
        items = self.fill(500)
        for item in items:
            item['record_bytes'] = 600000
            self.module._put(item)
        ids = self.module._pending('PENDING', 500, set(), self.context)
        self.assertGreaterEqual(len(ids), 100)
        self.assertLessEqual(len(ids) * 600000, self.module.MAX_BATCH_BYTES)
        self.assertGreater((len(ids) + 1) * 600000, self.module.MAX_BATCH_BYTES)

    def test_pending_index_pagination_and_stale_entries_are_safe(self):
        items = self.fill(100)
        stale = items[0]
        stale['status'] = 'DONE'
        self.module._put(stale)
        self.ddb.query.side_effect = [
            {'Items': [{'id': {'S': stale['id']}}], 'LastEvaluatedKey': {'id': {'S': stale['id']}}},
            {'Items': [{'id': {'S': item['id']}} for item in items[1:]]}
        ]
        selected = self.module._pending('PENDING', 500, set(), self.context)
        self.assertEqual(len(selected), 99)
        self.assertNotIn(stale['id'], selected)
        self.assertIn('ExclusiveStartKey', self.ddb.query.call_args.kwargs)

    def test_gsi_lag_cannot_select_already_owned_ids(self):
        self.fill(100)
        self.batch.create_model_invocation_job.side_effect = TimeoutError('interrupted')
        with self.assertRaises(TimeoutError):
            self.dispatch()
        job = self.active()[0]
        self.assertEqual(self.module._pending('PENDING', 500, set(job['ids']), self.context), [])

    def test_submission_timeout_reuses_persisted_idempotency_token(self):
        self.fill(100)
        self.batch.create_model_invocation_job.side_effect = TimeoutError('connection lost')
        with self.assertRaises(TimeoutError):
            self.dispatch()
        first = self.batch.create_model_invocation_job.call_args.kwargs
        self.assertEqual(self.active()[0]['phase'], 'PREPARING')
        self.batch.create_model_invocation_job.side_effect = self.create_job
        self.dispatch()
        second = self.batch.create_model_invocation_job.call_args.kwargs
        self.assertEqual(first, second)

    def test_partial_claiming_recovers_without_losing_chunks(self):
        self.fill(100)
        original = self.module._put
        calls = 0

        def interrupt(item):
            nonlocal calls
            if item.get('status') == 'BATCH':
                calls += 1
                if calls == 10:
                    raise TimeoutError('interrupted preparation')
            return original(item)

        with patch.object(self.module, '_put', side_effect = interrupt):
            with self.assertRaises(TimeoutError):
                self.dispatch()
        self.assertEqual(len(self.active()[0]['ids']), 100)
        self.dispatch()
        self.assertEqual(self.active()[0]['phase'], 'RUNNING')
        self.batch.create_model_invocation_job.assert_called_once()

    def test_preparation_checkpoints_skip_completed_parts(self):
        self.fill(100)
        original = self.module._put

        def interrupt(item):
            if item.get('status') == 'BATCH' and item['key'] == 'guides/chunk-30.md':
                raise TimeoutError('interrupted next part')
            return original(item)

        with patch.object(self.module, '_put', side_effect = interrupt):
            with self.assertRaises(TimeoutError):
                self.dispatch()
        self.assertEqual(self.active()[0]['preparedParts'], 1)
        self.s3.get_object.reset_mock()
        self.dispatch()
        prepared_keys = [call.kwargs['Key'] for call in self.s3.get_object.call_args_list
                         if call.kwargs['Key'].startswith('prepared/')]
        first = self.module._get(self.active()[0]['ids'][0])['prepared']
        self.assertNotIn(first, prepared_keys)

    def test_out_of_order_outputs_map_back_to_original_keys(self):
        items = self.fill(100)
        self.dispatch()
        job = self.active()[0]
        self.output(job, [{'recordId': item['id'], 'modelOutput': self.response}
                          for item in reversed(items)])
        self.assertEqual(self.dispatch()['activeJobs'], 0)
        for item in items:
            self.assertEqual(self.module._get(item['id'])['status'], 'DONE')
            self.assertEqual(self.objects[('nova-use2-lukach-io', item['key'])],
                             b'### Source\n\nFacts.')
        self.runtime.converse.assert_not_called()

    def test_errors_truncation_and_missing_results_become_failed(self):
        items = self.fill(100)
        self.dispatch()
        job = self.active()[0]
        truncated = copy.deepcopy(self.response)
        truncated['stopReason'] = 'max_tokens'
        self.output(job, [
            {'recordId': items[0]['id'], 'error': {'errorMessage': 'throttled'}},
            {'recordId': items[1]['id'], 'modelOutput': truncated},
        ] + [{'recordId': item['id'], 'modelOutput': self.response} for item in items[3:]])
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.dispatch()
        self.assertEqual([self.module._get(item['id'])['status'] for item in items[:4]],
                         ['FAILED', 'FAILED', 'FAILED', 'DONE'])
        self.assertNotIn(('nova-use2-lukach-io', items[1]['key']), self.objects)
        result = self.module.handler({'action': 'retry', 'ids': [item['id'] for item in items[:3]]},
                                     self.context)
        self.assertEqual(result, {'requeued': 3})
        self.dispatch()
        self.assertFalse(self.active())  # Fewer than 100 retries never cause paid padding.

    def test_failed_job_does_not_lose_records(self):
        items = self.fill(100)
        self.dispatch()
        self.jobs[self.active()[0]['arn']] = 'Failed'
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.dispatch()
        self.assertFalse(self.active())
        self.assertTrue(all(self.module._get(item['id'])['status'] == 'FAILED' for item in items))

    def test_deleted_output_for_processed_job_reports_clear_reason(self):
        items = self.fill(100)
        self.dispatch()
        self.jobs[self.active()[0]['arn']] = 'Completed'
        get_job = self.batch.get_model_invocation_job.side_effect
        self.batch.get_model_invocation_job.side_effect = lambda **kw: {
            **get_job(**kw), 'processedRecordCount': 100
        }
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.dispatch()
        self.assertIn('batch output may have been deleted',
                      self.module._get(items[0]['id'])['error'])

    def test_blank_output_lines_are_ignored(self):
        items = self.fill(100)
        self.dispatch()
        job = self.active()[0]
        self.output(job, [{'recordId': item['id'], 'modelOutput': self.response} for item in items])
        key = ('batch-use2-lukach-io', f"jobs/{job['id']}/raw/job/input.jsonl.out")
        self.objects[key] += b'\n\n'
        self.dispatch()
        self.assertFalse(self.active())
        self.assertEqual(self.module._get(items[0]['id'])['status'], 'DONE')

    def test_s3_write_failure_keeps_job_for_collection_retry(self):
        items = self.fill(100)
        self.dispatch()
        self.output(self.active()[0], [
            {'recordId': item['id'], 'modelOutput': self.response} for item in items
        ])
        self.s3.put_object.side_effect = RuntimeError('S3 unavailable')
        with self.assertRaises(RuntimeError):
            self.dispatch()
        self.assertEqual(self.module._get(items[0]['id'])['status'], 'BATCH')
        self.assertEqual(len(self.active()), 1)
        self.s3.put_object.side_effect = self.put_object
        self.dispatch()
        self.assertFalse(self.active())

    def test_collection_resumes_from_persisted_chunk_status(self):
        items = self.fill(100)
        self.dispatch()
        job = self.active()[0]
        self.output(job, [{'recordId': item['id'], 'modelOutput': self.response} for item in items])
        self.context.get_remaining_time_in_millis.side_effect = [900000, 900000, 1000]
        control = self.module._get('control')
        self.assertFalse(self.module._collect(control['active'][0], control, self.context))
        self.assertEqual(self.module._get(items[0]['id'])['status'], 'DONE')
        self.assertTrue(self.active()[0]['outputOffsets'])
        self.context.get_remaining_time_in_millis.side_effect = None
        self.ddb.get_item.reset_mock()
        self.dispatch()
        loaded_ids = [call.kwargs['Key']['id']['S'] for call in self.ddb.get_item.call_args_list]
        self.assertNotIn(items[0]['id'], loaded_ids)
        self.assertFalse(self.active())

    def test_missing_result_recovery_checkpoints_avoid_reprocessing(self):
        items = self.fill(100)
        self.dispatch()
        control = self.module._get('control')
        job = control['active'][0]
        self.jobs[job['arn']] = 'Failed'
        self.context.get_remaining_time_in_millis.side_effect = [900000, 1000]
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.assertFalse(self.module._collect(job, control, self.context))
        self.assertEqual(self.active()[0]['missingIndex'], 1)
        self.context.get_remaining_time_in_millis.side_effect = None
        first_id = sorted(item['id'] for item in items)[0]
        self.ddb.get_item.reset_mock()
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.dispatch()
        loaded_ids = [call.kwargs['Key']['id']['S'] for call in self.ddb.get_item.call_args_list]
        self.assertNotIn(first_id, loaded_ids)
        self.assertFalse(self.active())

    def test_unknown_output_id_is_not_written(self):
        self.fill(100)
        self.dispatch()
        self.output(self.active()[0], [{'recordId': 'unknown', 'modelOutput': self.response}])
        with self.assertRaises(ValueError):
            self.dispatch()
        self.assertTrue(self.active())

    def test_retry_cannot_race_active_collection(self):
        items = self.fill(100)
        self.dispatch()
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.module._fail(items[0], 'test failure')
        with self.assertRaises(ValueError):
            self.module.handler({'action': 'retry', 'ids': [items[0]['id']]}, self.context)

    def test_retry_rejects_duplicate_or_invalid_ids(self):
        for ids in ([], ['invalid'], [123], ['a' * 64, 'a' * 64]):
            with self.subTest(ids = ids), self.assertRaises(ValueError):
                self.module.handler({'action': 'retry', 'ids': ids}, self.context)

    def test_read_tests_prefix_is_batch_only(self):
        item = self.ingest('tests/sample.md')
        self.assertEqual(self.notify(item), {'batchItemFailures': []})
        self.fill(99)
        self.dispatch()
        self.batch.create_model_invocation_job.assert_called_once()
        self.assertEqual(self.ingest('tests/sample.md')['status'], 'BATCH')
        self.runtime.converse.assert_not_called()

    def test_flex_upload_automatically_processes_and_preserves_output_path(self):
        item = self.ingest('tests/my file+v2.md', bucket = 'flex-use2-lukach-io')
        self.assertEqual(item['status'], 'FLEX_PENDING')
        self.assertEqual(self.notify(item), {'batchItemFailures': []})
        self.assertEqual(self.runtime.converse.call_args.kwargs['serviceTier'], {'type': 'flex'})
        self.assertEqual(self.objects[('nova-use2-lukach-io', item['key'])],
                         b'### Source\n\nFacts.')
        self.batch.create_model_invocation_job.assert_not_called()
        self.notify(item)
        self.runtime.converse.assert_called_once()

    def test_flex_requires_markdown(self):
        with self.assertRaises(ValueError):
            self.ingest('guides/chunk.txt', bucket = 'flex-use2-lukach-io')
        self.runtime.converse.assert_not_called()

    def test_read_batch_tail_cannot_use_flex(self):
        item = self.ingest('guides/tail.md')
        self.notify(item)
        self.dispatch()
        self.assertEqual(self.module._get(item['id'])['status'], 'PENDING')
        with self.assertRaises(ValueError):
            self.module._process_flex(item, self.context)
        self.runtime.converse.assert_not_called()

    def test_flex_sources_are_not_selected_for_batch(self):
        item = self.ingest('guides/sample.md', bucket = 'flex-use2-lukach-io')
        self.fill(99)
        self.dispatch()
        self.batch.create_model_invocation_job.assert_not_called()
        self.assertEqual(self.module._get(item['id'])['status'], 'FLEX_PENDING')

    def test_removed_manual_flex_action_is_rejected(self):
        self.ingest('guides/sample.md')
        with self.assertRaises(ValueError):
            self.module.handler({'action': 'flex-test', 'key': 'guides/sample.md'}, self.context)
        self.runtime.converse.assert_not_called()

    def test_distinct_buckets_have_distinct_source_ids(self):
        batch_item = self.ingest('sample.md')
        flex_item = self.ingest('sample.md', bucket = 'flex-use2-lukach-io')
        self.assertNotEqual(batch_item['id'], flex_item['id'])
        self.assertEqual(batch_item['status'], 'PENDING')
        self.assertEqual(flex_item['status'], 'FLEX_PENDING')

    def test_flex_source_is_downloaded_with_event_etag(self):
        self.objects[('flex-use2-lukach-io', 'sample.md')] = b'Facts.'
        event = {'Records': [{
            'messageId': 'source-message', 'body': json.dumps({'Records': [{'s3': {
                'bucket': {'name': 'flex-use2-lukach-io'},
                'object': {'key': 'sample.md', 'sequencer': 'ABC123',
                           'eTag': hashlib.md5(b'Facts.').hexdigest()}
            }}]})
        }]}
        self.assertEqual(self.module.handler(event, self.context), {'batchItemFailures': []})
        self.s3.get_object.assert_any_call(
            Bucket = 'flex-use2-lukach-io', Key = 'sample.md',
            IfMatch = '"' + hashlib.md5(b'Facts.').hexdigest() + '"'
        )

    def test_pause_blocks_submission_but_resume_restores_it(self):
        self.fill(100)
        self.module.handler({'action': 'pause'}, self.context)
        self.assertTrue(self.dispatch()['paused'])
        self.batch.create_model_invocation_job.assert_not_called()
        self.module.handler({'action': 'resume'}, self.context)
        self.assertEqual(self.dispatch()['activeJobs'], 1)

    def test_paused_dispatch_still_collects_completed_jobs(self):
        items = self.fill(100)
        self.dispatch()
        self.output(self.active()[0], [{'recordId': item['id'], 'modelOutput': self.response}
                                     for item in items])
        self.module.handler({'action': 'pause'}, self.context)
        self.dispatch()
        self.assertFalse(self.active())

    def test_flex_retry_after_saved_output_does_not_repeat_inference(self):
        item = self.ingest('tests/sample.md', bucket = 'flex-use2-lukach-io')
        self.put_object(Bucket = 'nova-use2-lukach-io', Key = item['key'],
                        Body = b'### Saved', Metadata = {'source-id': item['id']})
        self.notify(item)
        self.runtime.converse.assert_not_called()

    def test_flex_error_is_visible_and_tracked(self):
        item = self.ingest('tests/sample.md', bucket = 'flex-use2-lukach-io')
        self.runtime.converse.side_effect = TimeoutError('FLEX timeout')
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.assertEqual(self.notify(item),
                             {'batchItemFailures': [{'itemIdentifier': 'source-message'}]})
        self.assertEqual(self.module._get(item['id'])['status'], 'FAILED')
        self.runtime.converse.side_effect = None
        self.assertEqual(self.notify(item), {'batchItemFailures': []})
        self.assertEqual(self.module._get(item['id'])['status'], 'DONE')

    def test_failed_flex_sources_cannot_be_requeued_to_batch(self):
        item = self.ingest('tests/sample.md', bucket = 'flex-use2-lukach-io')
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.module._fail(item, 'failure')
        with self.assertRaises(ValueError):
            self.module.handler({'action': 'retry', 'ids': [item['id']]}, self.context)
        self.assertEqual(self.module._get(item['id'])['status'], 'FAILED')

    def test_truncated_flex_response_retries_without_saving_output(self):
        item = self.ingest('tests/sample.md', bucket = 'flex-use2-lukach-io')
        self.runtime.converse.return_value['stopReason'] = 'max_tokens'
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.assertEqual(self.notify(item),
                             {'batchItemFailures': [{'itemIdentifier': 'source-message'}]})
        self.assertNotIn(('nova-use2-lukach-io', item['key']), self.objects)

    def test_insufficient_flex_time_does_not_call_model(self):
        item = self.ingest('tests/sample.md', bucket = 'flex-use2-lukach-io')
        self.context.get_remaining_time_in_millis.return_value = 800000
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.assertEqual(self.notify(item),
                             {'batchItemFailures': [{'itemIdentifier': 'source-message'}]})
        self.runtime.converse.assert_not_called()

    def test_invalid_source_is_not_registered(self):
        for body in (b'', b'\xff', b'x' * 100001):
            with self.subTest(body = len(body)), self.assertRaises((ValueError, UnicodeDecodeError)):
                self.ingest(body = body)
        self.assertFalse(self.items)

    def test_exact_chunk_byte_limit_is_accepted(self):
        item = self.ingest(body = b'x' * self.module.MAX_CHUNK_BYTES)
        self.assertEqual(item['status'], 'PENDING')
        with self.assertRaises(ValueError):
            self.ingest(sequencer = '2', body = b'x' * (self.module.MAX_CHUNK_BYTES + 1))

    def test_source_sequencer_is_required(self):
        with self.assertRaises(ValueError):
            self.ingest(sequencer = None)

    def test_reupload_of_identical_content_is_a_new_request(self):
        first = self.ingest()
        second = self.ingest(sequencer = '2')
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['etag'], second['etag'])

    def test_overwritten_unprepared_source_fails_without_inference(self):
        body = b'Original facts.'
        key = 'sample.md'
        self.objects[('flex-use2-lukach-io', key)] = b'New facts.'
        event = {'Records': [{
            'messageId': 'stale', 'body': json.dumps({'Records': [{'s3': {
                'bucket': {'name': 'flex-use2-lukach-io'},
                'object': {'key': key, 'sequencer': '1', 'eTag': hashlib.md5(body).hexdigest()}
            }}]})
        }]}
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.assertEqual(self.module.handler(event, self.context),
                             {'batchItemFailures': [{'itemIdentifier': 'stale'}]})
        self.runtime.converse.assert_not_called()
        self.assertFalse(self.items)

    def test_prepared_retry_does_not_reread_overwritten_source(self):
        item = self.ingest('sample.md', bucket = 'flex-use2-lukach-io')
        self.objects[('flex-use2-lukach-io', item['key'])] = b'Replacement content.'
        self.assertEqual(self.notify(item), {'batchItemFailures': []})
        request = self.runtime.converse.call_args.kwargs
        self.assertEqual(request['messages'][0]['content'][0]['text'], '## Source\n\nFacts.')

    def test_new_upload_overwrites_existing_nova_output(self):
        first = self.ingest('sample.md', bucket = 'flex-use2-lukach-io')
        self.notify(first)
        second = self.ingest('sample.md', sequencer = '2', bucket = 'flex-use2-lukach-io')
        self.runtime.converse.return_value['output']['message']['content'][0]['text'] = '### New edit'
        self.notify(second)
        self.assertEqual(self.runtime.converse.call_count, 2)
        self.assertEqual(self.objects[('nova-use2-lukach-io', 'sample.md')], b'### New edit')
        self.assertEqual(self.metadata[('nova-use2-lukach-io', 'sample.md')],
                         {'source-id': second['id']})

    def test_source_buckets_contain_only_sources(self):
        item = self.ingest('_batch/generated.md')
        self.assertEqual(item['status'], 'PENDING')
        self.assertEqual(sorted(self.objects),
                         [('batch-use2-lukach-io', item['prepared']),
                          ('read-use2-lukach-io', '_batch/generated.md')])

    def test_quota_reservations_survive_invocations(self):
        self.items['nova'] = {
            'id': {'S': 'nova'}, 'reservations': {'S': json.dumps([[100, 10], [101, 10]])}
        }
        with patch.object(self.module.time, 'time', side_effect = [110, 161]), \
             patch.object(self.module.time, 'sleep') as sleep:
            self.module.reserve_quota(20, self.context)
        sleep.assert_called_once_with(50)
        self.assertEqual(json.loads(self.items['nova']['reservations']['S']), [[161, 20]])

    def test_over_budget_flex_request_does_not_reserve(self):
        with self.assertRaises(ValueError):
            self.module.reserve_quota(100001, self.context)
        self.assertNotIn('nova', self.items)

    def test_notifications_report_partial_failures_and_acknowledge_tests(self):
        event = {'Records': [
            {'messageId': 'test', 'body': json.dumps({'Event': 's3:TestEvent'})},
            {'messageId': 'broken', 'body': 'invalid json'}
        ]}
        with self.assertLogs(self.module.logger, level = 'ERROR'):
            self.assertEqual(self.module.handler(event, self.context),
                             {'batchItemFailures': [{'itemIdentifier': 'broken'}]})

    def test_invalid_markdown_is_rejected(self):
        for text in ('', '# Chapter', '## Section', 'Title\n===', 'Title\n---',
                     '```markdown\n### Title\n```', '### Title\n\n```python\nprint(1)'):
            with self.subTest(text = text), self.assertRaises(ValueError):
                self.module.validate_markdown(text)

    def test_flex_markdown_wrapper_is_removed_before_saving(self):
        item = self.ingest('sample.md', bucket = 'flex-use2-lukach-io')
        self.runtime.converse.return_value['output']['message']['content'][0]['text'] = (
            '```markdown\n### Source\n\nFacts.\n```'
        )
        self.assertEqual(self.notify(item), {'batchItemFailures': []})
        self.assertEqual(self.objects[('nova-use2-lukach-io', item['key'])],
                         b'### Source\n\nFacts.\n')
        self.assertEqual(self.module._get(item['id'])['status'], 'DONE')
        self.runtime.converse.assert_called_once()

    def test_batch_wrappers_are_removed_before_saving(self):
        items = self.fill(100)
        self.dispatch()
        response = copy.deepcopy(self.response)
        response['output']['message']['content'][0]['text'] = '~~~md\n### Source\n\nFacts.\n~~~'
        self.output(self.active()[0], [
            {'recordId': item['id'], 'modelOutput': response} for item in items
        ])
        self.dispatch()
        self.assertFalse(self.active())
        for item in items:
            self.assertEqual(self.objects[('nova-use2-lukach-io', item['key'])],
                             b'### Source\n\nFacts.\n')

    def test_normalization_preserves_inner_content_and_code_fences(self):
        content = '### Title\r\n\r\n```python\r\n# comment\r\nprint(1)\r\n```\r\n'
        wrapped = '\r\n````MARKDOWN\r\n' + content + '````\r\n\r\n'
        normalized = self.module.normalize_markdown(wrapped)
        self.assertEqual(normalized, content)
        self.module.validate_markdown(normalized)
        for opener, closer in (('```', '```'), ('```md', '````'),
                               ('~~~markdown', '~~~')):
            self.assertEqual(self.module.normalize_markdown(opener + '\nFacts.\n' + closer),
                             'Facts.\n')

    def test_normalization_does_not_strip_legitimate_code_blocks(self):
        for text in ('```python\nprint(1)\n```',
                     '### Title\n\n```markdown\n### Example\n```\n',
                     '### Title\n\n```\ncode\n```\n'):
            self.assertEqual(self.module.normalize_markdown(text), text)
            self.module.validate_markdown(text)

    def test_malformed_or_ambiguous_wrappers_are_rejected(self):
        for text in ('```markdown\nFacts.', '````md\nFacts.\n```',
                     '```md\nFacts.\n~~~', '```md\nOne\n```\nTwo\n```'):
            with self.subTest(text = text), self.assertRaises(ValueError):
                self.module.normalize_markdown(text)

    def test_unwrapped_content_still_requires_validation(self):
        for text in ('```markdown\n# Chapter\n```', '~~~md\n\n~~~',
                     '````md\n### Title\n```python\nprint(1)\n````'):
            with self.subTest(text = text), self.assertRaises(ValueError):
                self.module.validate_markdown(self.module.normalize_markdown(text))

    def test_code_math_callouts_and_thematic_breaks_are_preserved(self):
        self.module.validate_markdown(
            '### Title\n\n> **Definition:** Fact.\n\n---\n\n'
            '```python\n# comment\n## comment\n```\n\n$$x=1$$'
        )

    def test_unknown_action_fails_explicitly(self):
        with self.assertRaises(ValueError):
            self.module.handler({'action': 'unknown'}, self.context)

    def test_sdk_has_no_automatic_inference_retries(self):
        self.config.assert_any_call(
            connect_timeout = 5, read_timeout = 780,
            retries = {'total_max_attempts': 1}
        )


if __name__ == '__main__':
    unittest.main()
