import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


def load():
    boto3 = MagicMock()
    module_path = Path(__file__).resolve().parents[1] / 'text2chunk' / 'text2chunk.py'
    spec = importlib.util.spec_from_file_location('text2chunk_handler', module_path)
    module = importlib.util.module_from_spec(spec)

    with patch.dict(sys.modules, {'boto3': boto3}):
        spec.loader.exec_module(module)

    return module, boto3.client.return_value


class Text2ChunkTests(unittest.TestCase):

    def test_packs_small_sections_together(self):
        module, _ = load()

        text = '# One\nalpha\n## Two\nbravo\n### Three\ncharlie\n'
        self.assertEqual(module.split(text), [text])

    def test_breaks_at_a_header_near_the_limit(self):
        module, _ = load()

        body = 'x'*9000+'\n'
        text = '# One\n'+body+'## Two\n'+body+'## Three\n'+body
        chunks = module.split(text)

        self.assertEqual(len(chunks), 3)
        self.assertTrue(chunks[0].startswith('# One\n'))
        self.assertTrue(chunks[1].startswith('## Two\n'))
        self.assertTrue(chunks[2].startswith('## Three\n'))

    def test_oversized_section_keeps_heading_context(self):
        module, _ = load()

        text = '# Big\n'+'paragraph\n\n'*4000
        chunks = module.split(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(chunks[0].startswith('# Big\n'))
        for chunk in chunks[1:]:
            self.assertTrue(chunk.startswith('# Big (continued)\n\n'))

    def test_splits_on_character_limit(self):
        module, _ = load()

        line = 'x'*999+'\n'
        chunks = module.split(line*20)

        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= module.LIMIT for chunk in chunks))

    def test_keeps_tables_and_code_fences_intact(self):
        module, _ = load()

        table = '| a | b |\n| - | - |\n| 1 | 2 |\n'
        fence = '```python\nprint(1)\n\nprint(2)\n```\n'
        text = '# Big\n'+('filler\n\n'*2000)+table+'\n'+fence+('filler\n\n'*2000)
        chunks = module.split(text)

        joined = ' '.join(chunks)
        self.assertEqual(joined.count('| a | b |'), 1)
        self.assertTrue(any(table in chunk for chunk in chunks))
        self.assertTrue(any(fence in chunk for chunk in chunks))

    def test_preamble_omits_missing_context(self):
        module, _ = load()

        self.assertEqual(
            module.preamble('a/b.md', 'Guide', 'Guide', 1, 3),
            '> Source: a/b.md\n> Document: Guide\n> Chunk 1 of 3\n\n'
        )
        self.assertEqual(
            module.preamble('a/b.md', '', '', 2, 3),
            '> Source: a/b.md\n> Chunk 2 of 3\n\n'
        )

    def test_uploads_flat_numbered_chunks_and_cleans_tmp(self):
        module, s3 = load()

        s3.get_paginator.return_value.paginate.return_value = [
            {'Contents': [{'Key': 'notes/ignore.txt'}, {'Key': 'notes/my guide.md'}]}
        ]

        def download_file(bucket, key, path):
            with open(path, 'w', encoding = 'utf-8') as f:
                f.write('# One\n'+'x'*9000+'\n# Two\n'+'y'*9000+'\n')

        s3.download_file.side_effect = download_file

        uploads = []
        s3.upload_file.side_effect = lambda path, bucket, key, ExtraArgs: uploads.append(
            (key, bucket, Path(path).read_text(encoding = 'utf-8'))
        )

        with patch.dict(os.environ, {'MD_BUCKET': 'md-use2-lukach-io',
                                     'CHUNK_BUCKET': 'chunk-use2-lukach-io'}):
            module.handler({}, None)

        self.assertEqual(uploads, [
            ('my guide-0001.md', 'chunk-use2-lukach-io',
             '> Source: notes/my guide.md\n> Document: One\n> Chunk 1 of 2\n\n'
             '# One\n'+'x'*9000+'\n'),
            ('my guide-0002.md', 'chunk-use2-lukach-io',
             '> Source: notes/my guide.md\n> Document: One\n> Section: Two\n> Chunk 2 of 2\n\n'
             '# Two\n'+'y'*9000+'\n')
        ])

        leftovers = [name for name in os.listdir('/tmp') if name.endswith('.md')]
        self.assertEqual(leftovers, [])

    def test_handles_s3_event_records(self):
        module, s3 = load()

        def download_file(bucket, key, path):
            with open(path, 'w', encoding = 'utf-8') as f:
                f.write('# One\nalpha\n')

        s3.download_file.side_effect = download_file

        event = {'Records': [
            {'s3': {'bucket': {'name': 'md-use2-lukach-io'},
                    'object': {'key': 'notes%2Fignore.txt'}}},
            {'s3': {'bucket': {'name': 'md-use2-lukach-io'},
                    'object': {'key': 'notes%2Fmy+guide.md'}}}
        ]}

        with patch.dict(os.environ, {'MD_BUCKET': 'md-use2-lukach-io',
                                     'CHUNK_BUCKET': 'chunk-use2-lukach-io'}):
            module.handler(event, None)

        s3.get_paginator.assert_not_called()
        s3.download_file.assert_called_once()
        self.assertEqual(s3.download_file.call_args[0][:2], ('md-use2-lukach-io', 'notes/my guide.md'))
        self.assertEqual(s3.upload_file.call_args[0][2], 'my guide-0001.md')


if __name__ == '__main__':
    unittest.main()
