import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


def load():
    boto3 = MagicMock()
    module_path = Path(__file__).resolve().parents[1] / 'chunk2read' / 'chunk2read.py'
    spec = importlib.util.spec_from_file_location('chunk2read_handler', module_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'boto3': boto3}):
        spec.loader.exec_module(module)
    return module, boto3.client.return_value


class Chunk2ReadTests(unittest.TestCase):

    def setUp(self):
        self.module, self.s3 = load()
        environment = patch.dict(os.environ, {
            'CHUNK_BUCKET': 'chunks', 'NOVA_BUCKET': 'nova',
            'READ_BUCKET': 'read', 'FLEX_BUCKET': 'flex'
        })
        environment.start()
        self.addCleanup(environment.stop)

    def pages(self, chunks, nova):
        self.s3.get_paginator.return_value.paginate.side_effect = (
            lambda Bucket: nova if Bucket == 'nova' else chunks
        )

    def test_exact_batch_boundaries(self):
        for count in (0, 1, 99, 100, 101, 199, 200, 250):
            with self.subTest(count = count):
                self.s3.reset_mock()
                keys = [f'guides/chunk-{number:04d}.md' for number in range(count)]
                self.pages([{'Contents': [{'Key': key} for key in keys]}], [{}])
                with patch.object(self.module, '_copy_batch',
                                  wraps = self.module._copy_batch) as copy_batch:
                    result = self.module.handler({}, None)
                read = count // 100 * 100
                self.assertEqual(result, {
                    'read': read, 'read_batches': count // 100,
                    'flex': count % 100, 'skipped_nova': 0
                })
                self.assertEqual(
                    [(call.args[2], len(call.args[3])) for call in copy_batch.call_args_list],
                    [('read', 100)] * (count // 100)
                    + ([('flex', count % 100)] if count % 100 else [])
                )
                copies = self.s3.copy.call_args_list
                self.assertEqual(len(copies), count)
                self.assertEqual(
                    {call.args[2] for call in copies}, set(keys)
                )
                for call in copies:
                    source, bucket, key = call.args
                    self.assertEqual(source, {'Bucket': 'chunks', 'Key': key})
                    self.assertEqual(bucket, 'read' if key in keys[:read] else 'flex')
                self.s3.delete_object.assert_not_called()

    def test_excludes_nova_keys_across_pages_before_batching(self):
        keys = [f'chunk-{number:04d}.md' for number in range(1203)]
        self.pages(
            [{'Contents': [{'Key': key} for key in keys[:1000]]},
             {}, {'Contents': [{'Key': key} for key in keys[1000:]]}],
            [{'Contents': [{'Key': key} for key in keys[:1000]]},
             {'Contents': [{'Key': key} for key in keys[1000:1102]]}]
        )
        result = self.module.handler({}, None)
        self.assertEqual(result, {
            'read': 100, 'read_batches': 1, 'flex': 1, 'skipped_nova': 1102
        })
        self.assertEqual(
            {call.args[2] for call in self.s3.copy.call_args_list}, set(keys[1102:])
        )
        self.assertEqual(
            [call.kwargs for call in self.s3.get_paginator.return_value.paginate.call_args_list],
            [{'Bucket': 'nova'}, {'Bucket': 'chunks'}]
        )

    def test_all_completed_files_are_skipped(self):
        pages = [{'Contents': [{'Key': 'already.md'}]}]
        self.pages(pages, pages)
        self.assertEqual(self.module.handler({}, None), {
            'read': 0, 'read_batches': 0, 'flex': 0, 'skipped_nova': 1
        })
        self.s3.copy.assert_not_called()

    def test_all_file_types_and_special_keys_are_preserved(self):
        keys = ['folder/a + b.md', 'notes.txt', 'UPPER.MD']
        self.pages([{'Contents': [{'Key': key} for key in keys]}], [])
        self.module.handler({}, None)
        self.assertEqual(
            {call.args[2] for call in self.s3.copy.call_args_list}, set(keys)
        )

    def test_listing_errors_fail_invocation(self):
        self.s3.get_paginator.return_value.paginate.side_effect = RuntimeError('AccessDenied')
        with self.assertRaisesRegex(RuntimeError, 'AccessDenied'):
            self.module.handler({}, None)
        self.s3.copy.assert_not_called()

    def test_copy_errors_fail_invocation(self):
        self.pages([{'Contents': [{'Key': 'chunk.md'}]}], [])
        self.s3.copy.side_effect = RuntimeError('copy failed')
        with self.assertRaisesRegex(RuntimeError, 'copy failed'):
            self.module.handler({}, None)

    def test_failed_read_batch_does_not_copy_tail_to_flex(self):
        self.pages(
            [{'Contents': [{'Key': f'{number}.md'} for number in range(101)]}], []
        )
        self.s3.copy.side_effect = RuntimeError('copy failed')
        with self.assertRaisesRegex(RuntimeError, 'copy failed'):
            self.module.handler({}, None)
        self.assertTrue(self.s3.copy.called)
        self.assertTrue(all(call.args[1] == 'read'
                            for call in self.s3.copy.call_args_list))


if __name__ == '__main__':
    unittest.main()
