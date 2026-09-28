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
        converter.to_markdown.assert_called_once_with('/tmp/input.pdf', force_ocr=False)
        boto3.client.return_value.put_object.assert_called_once_with(
            Bucket='md-use2-lukach-io',
            Key='notes/my guide+v2.md',
            Body=b'# Converted',
            ContentType='text/markdown; charset=utf-8'
        )

    def test_handler_processes_only_one_pdf_record_per_invocation(self):
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
                    'object': {'key': 'notes%2Ffirst.pdf'}}},
            {'s3': {'bucket': {'name': 'pdf-use2-lukach-io'},
                    'object': {'key': 'notes%2Fsecond.pdf'}}},
        ]}

        with patch.dict(os.environ, {'MD_BUCKET': 'md-use2-lukach-io'}):
            module.handler(event, None)

        self.assertEqual(boto3.client.return_value.download_file.call_count, 1)
        boto3.client.return_value.download_file.assert_called_once_with(
            'pdf-use2-lukach-io', 'notes/first.pdf', '/tmp/input.pdf'
        )
        self.assertEqual(converter.to_markdown.call_count, 1)
        converter.to_markdown.assert_called_once_with('/tmp/input.pdf', force_ocr=False)
        self.assertEqual(boto3.client.return_value.put_object.call_count, 1)

    def test_large_pdf_is_split_into_page_chunks(self):
        boto3 = MagicMock()
        converter = MagicMock()
        converter.to_markdown.return_value = '# Converted'
        fitz = MagicMock()
        module_path = Path(__file__).resolve().parents[1] / 'pdf2md' / 'pdf2md.py'
        spec = importlib.util.spec_from_file_location('pdf2md_handler', module_path)
        module = importlib.util.module_from_spec(spec)

        with patch.dict(sys.modules, {'boto3': boto3, 'pymupdf4llm': converter, 'fitz': fitz}):
            spec.loader.exec_module(module)

        doc = MagicMock()
        doc.page_count = 60
        fitz.open.return_value = doc

        with patch.object(module, '_convert_pdf_in_chunks', return_value='# Part 1\n\n# Part 2') as chunker:
            with patch.dict(os.environ, {'MD_BUCKET': 'md-use2-lukach-io'}):
                module.handler({'Records': [{'s3': {'bucket': {'name': 'pdf-use2-lukach-io'}, 'object': {'key': 'notes%2Fbig.pdf'}}}]}, None)

        chunker.assert_called_once_with('/tmp/input.pdf', chunk_size=25)


if __name__ == '__main__':
    unittest.main()