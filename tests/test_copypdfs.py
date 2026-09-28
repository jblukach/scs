import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


class CopyPdfsTests(unittest.TestCase):

    def test_copies_every_page_with_unchanged_keys(self):
        boto3 = MagicMock()
        s3 = boto3.client.return_value
        s3.get_paginator.return_value.paginate.return_value = [
            {'Contents': [{'Key': 'guides/first.pdf'}, {'Key': 'spaces/a + b.PDF'}]},
            {},
            {'Contents': [{'Key': 'other/readme.txt'}]}
        ]
        module_path = Path(__file__).resolve().parents[1] / 'copypdfs' / 'copypdfs.py'
        spec = importlib.util.spec_from_file_location('copypdfs_handler', module_path)
        module = importlib.util.module_from_spec(spec)

        with patch.dict(sys.modules, {'boto3': boto3}):
            spec.loader.exec_module(module)

        with patch.dict(os.environ, {
            'SOURCE_BUCKET': 'scs-use2-lukach-io',
            'DESTINATION_BUCKET': 'pdf-use2-lukach-io'
        }):
            result = module.handler({}, None)

        s3.get_paginator.assert_called_once_with('list_objects_v2')
        s3.get_paginator.return_value.paginate.assert_called_once_with(
            Bucket='scs-use2-lukach-io'
        )
        self.assertEqual(
            [call.args for call in s3.copy.call_args_list],
            [
                ({'Bucket': 'scs-use2-lukach-io', 'Key': key}, 'pdf-use2-lukach-io', key)
                for key in ['guides/first.pdf', 'spaces/a + b.PDF', 'other/readme.txt']
            ]
        )
        self.assertEqual(result, {
            'source': 'scs-use2-lukach-io',
            'destination': 'pdf-use2-lukach-io',
            'copied': 3
        })


if __name__ == '__main__':
    unittest.main()