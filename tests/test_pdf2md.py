import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


class Pdf2MdTests(unittest.TestCase):

    def test_uploaded_pdf_preserves_path_and_decodes_key(self):
        boto3 = MagicMock()
        converter = MagicMock()
        converter.to_markdown.return_value = '# Converted'
        module_path = Path(__file__).resolve().parents[1] / 'pdf2md' / 'pdf2md.py'
        spec = importlib.util.spec_from_file_location('pdf2md_handler', module_path)
        module = importlib.util.module_from_spec(spec)

        with patch.dict(sys.modules, {'boto3': boto3, 'pymupdf4llm': converter}):
            spec.loader.exec_module(module)

        event = {'Records': [
            {'s3': {'bucket': {'name': 'pdf-use2-lukach-io'},
                    'object': {'key': 'notes%2Fignore.txt'}}},
            {'s3': {'bucket': {'name': 'pdf-use2-lukach-io'},
                    'object': {'key': 'notes%2Fmy+guide%2Bv2.PDF'}}}
        ]}
        with patch.dict(os.environ, {'MD_BUCKET': 'md-use2-lukach-io'}):
            module.handler(event, None)

        boto3.client.return_value.download_file.assert_called_once_with(
            'pdf-use2-lukach-io', 'notes/my guide+v2.PDF', '/tmp/input.pdf'
        )
        converter.to_markdown.assert_called_once_with('/tmp/input.pdf')
        boto3.client.return_value.put_object.assert_called_once_with(
            Bucket='md-use2-lukach-io',
            Key='notes/my guide+v2.md',
            Body=b'# Converted',
            ContentType='text/markdown; charset=utf-8'
        )


if __name__ == '__main__':
    unittest.main()