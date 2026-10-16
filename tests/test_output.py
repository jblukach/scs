import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


def load():
    module_path = Path(__file__).resolve().parents[1] / 'output' / 'output.py'
    spec = importlib.util.spec_from_file_location('output_handler', module_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'boto3': MagicMock()}):
        spec.loader.exec_module(module)
    return module, module.s3


class OutputTests(unittest.TestCase):

    def setUp(self):
        self.module, self.s3 = load()
        environment = patch.dict(os.environ, {
            'CHUNK_BUCKET': 'chunks', 'NOVA_BUCKET': 'nova', 'OUT_BUCKET': 'out'
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.uploads = {}
        self.s3.upload_fileobj.side_effect = self.upload

    def upload(self, file, bucket, key, ExtraArgs):
        self.assertEqual(bucket, 'out')
        self.assertEqual(ExtraArgs, {'ContentType': 'text/markdown; charset=utf-8'})
        self.uploads[key] = file.read()

    def inventory(self, chunks, nova=None):
        inventories = {'chunks': chunks, 'nova': chunks if nova is None else nova}
        self.s3.get_paginator.return_value.paginate.side_effect = lambda Bucket: (
            [{'Contents': [{'Key': key} for key in inventories[Bucket][:2]]},
             {}, {'Contents': [{'Key': key} for key in inventories[Bucket][2:]]}]
        )

    def test_reassembles_split_and_unsplit_documents_in_exact_order(self):
        keys = [
            'guide-0002-0001.md', 'guide-0001-0002.md', 'guide-0001-0001.md',
            'folder/other guide-0002.md', 'folder/other guide-0001.md'
        ]
        self.inventory(keys+['ignore.txt'])
        bodies = {key: ('# '+key+'\nR\u00e9sum\u00e9\n').encode() for key in keys}
        streams = []

        def get_object(Bucket, Key):
            self.assertEqual(Bucket, 'nova')
            stream = io.BytesIO(bodies[Key])
            streams.append(stream)
            return {'Body': stream}

        self.s3.get_object.side_effect = get_object
        result = self.module.handler({}, None)
        self.assertEqual(result, {'bucket': 'out', 'documents': 2, 'chunks': 5})
        self.assertEqual(self.uploads, {
            'guide.md': b'\n\n'.join(bodies[key] for key in [
                'guide-0001-0001.md', 'guide-0001-0002.md', 'guide-0002-0001.md'
            ]),
            'folder/other guide.md': b'\n\n'.join(bodies[key] for key in [
                'folder/other guide-0001.md', 'folder/other guide-0002.md'
            ])
        })
        self.assertTrue(all(stream.closed for stream in streams))
        self.s3.delete_object.assert_not_called()

    def test_numeric_order_beyond_four_digits(self):
        keys = {f'guide-{number:04d}.md' for number in range(1, 10002)}
        ordered = self.module._documents(keys)['guide.md']
        self.assertEqual(ordered[9998:], [
            'guide-9999.md', 'guide-10000.md', 'guide-10001.md'
        ])

    def test_missing_nova_result_prevents_all_writes(self):
        self.inventory(['ready-0001.md', 'missing-0001.md'], ['ready-0001.md'])
        with self.assertRaisesRegex(ValueError, '1 missing results'):
            self.module.handler({}, None)
        self.s3.get_object.assert_not_called()
        self.s3.upload_fileobj.assert_not_called()

    def test_unexpected_nova_markdown_fails_instead_of_merging_stale_results(self):
        self.inventory(['guide-0001.md'], ['guide-0001.md', 'guide-0002.md'])
        with self.assertRaisesRegex(ValueError, '1 unexpected results'):
            self.module.handler({}, None)
        self.s3.upload_fileobj.assert_not_called()

    def test_invalid_or_incomplete_numbering_prevents_all_writes(self):
        cases = (
            ['unnumbered.md'], ['guide-0000.md'], ['guide-0000-0001.md'],
            ['guide-0002.md'], ['guide-0001.md', 'guide-0003.md'],
            ['guide-0002-0001.md'],
            ['guide-0001-0001.md', 'guide-0003-0001.md'],
            ['guide-0001.md', 'guide-0001-0001.md'],
            ['guide-0001.md', 'guide-00001.md']
        )
        for keys in cases:
            with self.subTest(keys=keys):
                self.inventory(keys)
                with self.assertRaises(ValueError):
                    self.module.handler({}, None)
                self.s3.upload_fileobj.assert_not_called()

    def test_empty_inventory_is_logged_no_op(self):
        self.inventory([])
        with self.assertLogs(self.module.logger, level='INFO'):
            result = self.module.handler({}, None)
        self.assertEqual(result, {'bucket': 'out', 'documents': 0, 'chunks': 0})
        self.s3.upload_fileobj.assert_not_called()

    def test_empty_result_is_not_published(self):
        self.inventory(['guide-0001.md'])
        stream = io.BytesIO()
        self.s3.get_object.return_value = {'Body': stream}
        with self.assertRaisesRegex(ValueError, 'Empty Nova result'):
            self.module.handler({}, None)
        self.assertTrue(stream.closed)
        self.s3.upload_fileobj.assert_not_called()

    def test_listing_read_and_upload_errors_fail_invocation(self):
        for operation in ('list', 'read', 'upload'):
            with self.subTest(operation=operation):
                self.module, self.s3 = load()
                self.s3.upload_fileobj.side_effect = self.upload
                self.inventory(['guide-0001.md'])
                self.s3.get_object.return_value = {'Body': io.BytesIO(b'notes')}
                if operation == 'list':
                    target = self.s3.get_paginator.return_value.paginate
                elif operation == 'read':
                    target = self.s3.get_object
                else:
                    target = self.s3.upload_fileobj
                target.side_effect = RuntimeError(operation+' failed')
                with self.assertRaisesRegex(RuntimeError, operation+' failed'):
                    self.module.handler({}, None)

    def test_rerun_replaces_the_same_output_key(self):
        self.inventory(['guide-0001.md'])
        self.s3.get_object.side_effect = [
            {'Body': io.BytesIO(b'first')}, {'Body': io.BytesIO(b'second')}
        ]
        self.module.handler({}, None)
        self.module.handler({}, None)
        self.assertEqual(self.uploads, {'guide.md': b'second'})


if __name__ == '__main__':
    unittest.main()
