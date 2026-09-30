import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, call, patch


class Raw2SplitTests(unittest.TestCase):

    def test_splits_pdf_into_flat_numbered_parts(self):
        boto3 = MagicMock()
        pymupdf = MagicMock()
        module_path = Path(__file__).resolve().parents[1] / 'raw2split' / 'raw2split.py'
        spec = importlib.util.spec_from_file_location('raw2split_handler', module_path)
        module = importlib.util.module_from_spec(spec)

        with patch.dict(sys.modules, {'boto3': boto3, 'pymupdf': pymupdf}):
            spec.loader.exec_module(module)

        s3 = boto3.client.return_value
        s3.get_object.return_value = {'Body': MagicMock(read = MagicMock(return_value = b'%PDF'))}

        doc = pymupdf.open.return_value.__enter__.return_value
        doc.page_count = 2500

        parts = [MagicMock(), MagicMock(), MagicMock()]
        for index, part in enumerate(parts, start = 1):
            part.tobytes.return_value = b'part'+str(index).encode()
        pymupdf.open.side_effect = [pymupdf.open.return_value] + parts

        event = {'Records': [
            {'s3': {'bucket': {'name': 'raw-use2-lukach-io'},
                    'object': {'key': 'notes%2Fignore.txt'}}},
            {'s3': {'bucket': {'name': 'raw-use2-lukach-io'},
                    'object': {'key': 'notes%2Fmy+guide%2Bv2.PDF'}}}
        ]}
        with patch.dict(os.environ, {'SPLIT_BUCKET': 'split-use2-lukach-io'}):
            module.handler(event, None)

        s3.get_object.assert_called_once_with(Bucket = 'raw-use2-lukach-io', Key = 'notes/my guide+v2.PDF')

        parts[0].insert_pdf.assert_called_once_with(doc, from_page = 0, to_page = 999)
        parts[1].insert_pdf.assert_called_once_with(doc, from_page = 1000, to_page = 1999)
        parts[2].insert_pdf.assert_called_once_with(doc, from_page = 2000, to_page = 2499)

        self.assertEqual(s3.put_object.call_args_list, [
            call(Bucket = 'split-use2-lukach-io', Key = 'my guide+v2-0001.pdf',
                 Body = b'part1', ContentType = 'application/pdf'),
            call(Bucket = 'split-use2-lukach-io', Key = 'my guide+v2-0002.pdf',
                 Body = b'part2', ContentType = 'application/pdf'),
            call(Bucket = 'split-use2-lukach-io', Key = 'my guide+v2-0003.pdf',
                 Body = b'part3', ContentType = 'application/pdf')
        ])


if __name__ == '__main__':
    unittest.main()
