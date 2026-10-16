import logging
import os
import re
import shutil
import tempfile

import boto3

s3 = boto3.client('s3')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CHUNK_KEY = re.compile(r'^(.+?)(?:-([0-9]{4,}))?-([0-9]{4,})\.md$', re.IGNORECASE)


def _keys(bucket: str) -> set[str]:
    paginator = s3.get_paginator('list_objects_v2')
    return {
        item['Key']
        for page in paginator.paginate(Bucket = bucket)
        for item in page.get('Contents', [])
        if item['Key'].lower().endswith('.md')
    }


def _documents(keys: set[str]) -> dict[str, list[str]]:
    groups: dict[str, dict[int, dict[int, str]]] = {}
    for key in sorted(keys):
        match = CHUNK_KEY.fullmatch(key)
        if not match:
            raise ValueError('Unrecognized chunk key: '+key)
        base, part, chunk = match.groups()
        part_number = int(part) if part is not None else 0
        chunk_number = int(chunk)
        if chunk_number == 0 or (part is not None and part_number == 0):
            raise ValueError('Chunk and part numbers must start at 1: '+key)
        chunks = groups.setdefault(base+'.md', {}).setdefault(part_number, {})
        if chunk_number in chunks:
            raise ValueError('Duplicate chunk position: '+key)
        chunks[chunk_number] = key

    documents = {}
    for destination, parts in sorted(groups.items()):
        numbers = sorted(parts)
        if numbers != [0] and numbers != list(range(1, len(numbers)+1)):
            raise ValueError('Missing or mixed PDF parts for '+destination)
        ordered = []
        for part in numbers:
            chunks = parts[part]
            if sorted(chunks) != list(range(1, len(chunks)+1)):
                raise ValueError('Missing chunk numbers for '+destination)
            ordered.extend(chunks[number] for number in sorted(chunks))
        documents[destination] = ordered
    return documents


def handler(event, context) -> dict:
    chunk_bucket = os.environ['CHUNK_BUCKET']
    nova_bucket = os.environ['NOVA_BUCKET']
    out_bucket = os.environ['OUT_BUCKET']

    expected = _keys(chunk_bucket)
    completed = _keys(nova_bucket)
    missing = expected - completed
    unexpected = completed - expected
    if missing or unexpected:
        raise ValueError(
            f'Nova inventory mismatch: {len(missing)} missing results, '
            f'{len(unexpected)} unexpected results; '
            f'missing sample={sorted(missing)[:10]}, '
            f'unexpected sample={sorted(unexpected)[:10]}'
        )
    documents = _documents(expected)

    for destination, keys in documents.items():
        with tempfile.TemporaryFile() as output:
            for number, key in enumerate(keys):
                if number:
                    output.write(b'\n\n')
                start = output.tell()
                response = s3.get_object(Bucket = nova_bucket, Key = key)
                body = response['Body']
                try:
                    shutil.copyfileobj(body, output)
                finally:
                    body.close()
                if output.tell() == start:
                    raise ValueError('Empty Nova result: '+key)
            output.seek(0)
            s3.upload_fileobj(
                output, out_bucket, destination,
                ExtraArgs = {'ContentType': 'text/markdown; charset=utf-8'}
            )
        logger.info('Assembled %s from %s Nova chunks', destination, len(keys))

    result = {
        'bucket': out_bucket,
        'documents': len(documents),
        'chunks': len(expected)
    }
    logger.info('output complete: %s', result)
    return result
