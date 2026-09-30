import concurrent.futures
import os
import shutil
import tempfile
from urllib.parse import unquote_plus

import boto3

s3 = boto3.client('s3')

LIMIT = 15000
HEADERS = ('# ', '## ')
SUBHEADERS = ('### ', '#### ', '##### ', '###### ')
WORKERS = 8


def _headers(text, prefixes):
    blocks = []
    current = []

    for line in text.splitlines(keepends = True):
        if current and line.startswith(prefixes):
            blocks.append(''.join(current))
            current = []
        current.append(line)

    if current:
        blocks.append(''.join(current))

    return blocks


def _lines(text):
    """Line atoms, with fenced code blocks and table rows held together."""
    atoms = []
    current = []
    fence = False

    for line in text.splitlines(keepends = True):
        stripped = line.lstrip()

        if fence:
            current.append(line)
            if stripped.startswith('```'):
                fence = False
                atoms.append(''.join(current))
                current = []
            continue

        if stripped.startswith('```'):
            if current:
                atoms.append(''.join(current))
                current = []
            current.append(line)
            fence = True
            continue

        if stripped.startswith('|'):
            current.append(line)
            continue

        if current:
            atoms.append(''.join(current))
            current = []
        atoms.append(line)

    if current:
        atoms.append(''.join(current))

    return atoms


def _paragraphs(text):
    blocks = []
    current = []

    for atom in _lines(text):
        current.append(atom)
        if not atom.strip():
            blocks.append(''.join(current))
            current = []

    if current:
        blocks.append(''.join(current))

    return blocks


def _characters(text):
    return [text[start:start+LIMIT] for start in range(0, len(text), LIMIT)]


SPLITTERS = [
    lambda text: _headers(text, SUBHEADERS),
    _paragraphs,
    _lines,
    _characters
]


def _pack(pieces):
    chunks = []
    current = ''

    for piece in pieces:
        if current and len(current)+len(piece) > LIMIT:
            chunks.append(current)
            current = ''
        current += piece

    if current:
        chunks.append(current)

    return chunks


def _fit(block, level = 0):
    if len(block) <= LIMIT or level >= len(SPLITTERS):
        return [block]

    pieces = SPLITTERS[level](block)
    if len(pieces) < 2:
        return _fit(block, level+1)

    fitted = []
    for piece in _pack(pieces):
        fitted.extend(_fit(piece, level+1))

    return fitted


def split(text):
    chunks = []

    for block in _pack(_headers(text, HEADERS)):
        if len(block) <= LIMIT:
            chunks.append(block)
            continue

        heading = block.splitlines()[0] if block.startswith(HEADERS) else ''

        for number, piece in enumerate(_fit(block)):
            if number and heading:
                piece = heading+' (continued)\n\n'+piece
            chunks.append(piece)

    return [chunk for chunk in chunks if chunk.strip()]


def _title(text):
    for line in text.splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return ''


def _heading(chunk):
    for line in chunk.splitlines():
        if line.startswith(HEADERS):
            return line.lstrip('#').strip().removesuffix(' (continued)')
    return ''


def preamble(source, title, heading, number, total):
    lines = ['> Source: '+source]

    if title:
        lines.append('> Document: '+title)
    if heading and heading != title:
        lines.append('> Section: '+heading)

    lines.append('> Chunk '+str(number)+' of '+str(total))

    return '\n'.join(lines)+'\n\n'


def _chunk(md_bucket, chunk_bucket, key):
    base = os.path.basename(key)[:-3]
    workdir = tempfile.mkdtemp(dir = '/tmp')

    try:
        source = os.path.join(workdir, 'source.md')
        s3.download_file(md_bucket, key, source)

        with open(source, encoding = 'utf-8') as f:
            text = f.read()

        os.remove(source)

        chunks = split(text)
        title = _title(text)

        for number, chunk in enumerate(chunks, start = 1):
            chunk_key = base+'-'+str(number).zfill(4)+'.md'
            chunk_path = os.path.join(workdir, chunk_key)
            body = preamble(key, title, _heading(chunk), number, len(chunks))+chunk

            with open(chunk_path, 'w', encoding = 'utf-8') as f:
                f.write(body)

            s3.upload_file(
                chunk_path,
                chunk_bucket,
                chunk_key,
                ExtraArgs = {'ContentType': 'text/markdown; charset=utf-8'}
            )
            os.remove(chunk_path)

        print('CHUNKED '+key+' -> '+str(len(chunks))+' chunks')
    finally:
        shutil.rmtree(workdir, ignore_errors = True)


def handler(event, context):
    md_bucket = os.environ['MD_BUCKET']
    chunk_bucket = os.environ['CHUNK_BUCKET']

    for record in event.get('Records', []):
        key = unquote_plus(record['s3']['object']['key'])
        if key.lower().endswith('.md'):
            _chunk(record['s3']['bucket']['name'], chunk_bucket, key)

    if event.get('Records'):
        return

    paginator = s3.get_paginator('list_objects_v2')

    keys = [
        item['Key']
        for page in paginator.paginate(Bucket = md_bucket)
        for item in page.get('Contents', [])
        if item['Key'].lower().endswith('.md')
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers = WORKERS) as pool:
        futures = [pool.submit(_chunk, md_bucket, chunk_bucket, key) for key in keys]
        for future in concurrent.futures.as_completed(futures):
            future.result()
