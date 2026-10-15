import concurrent.futures
import logging
import os

import boto3

s3 = boto3.client('s3')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BATCH_SIZE = 100
WORKERS = 8


def _keys(bucket: str):
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket = bucket):
        for item in page.get('Contents', []):
            yield item['Key']


def _copy_batch(pool, source: str, destination: str, keys: list[str]) -> None:
    futures = [
        pool.submit(
            s3.copy, {'Bucket': source, 'Key': key}, destination, key
        )
        for key in keys
    ]
    for future in concurrent.futures.as_completed(futures):
        future.result()
    logger.info('Copied %s chunks from %s to %s', len(keys), source, destination)


def handler(event, context) -> dict:
    chunk_bucket = os.environ['CHUNK_BUCKET']
    nova_bucket = os.environ['NOVA_BUCKET']
    read_bucket = os.environ['READ_BUCKET']
    flex_bucket = os.environ['FLEX_BUCKET']

    completed = set(_keys(nova_bucket))
    pending = []
    read = 0
    skipped = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers = WORKERS) as pool:
        for key in _keys(chunk_bucket):
            if key in completed:
                skipped += 1
                continue
            pending.append(key)
            if len(pending) == BATCH_SIZE:
                _copy_batch(pool, chunk_bucket, read_bucket, pending)
                read += BATCH_SIZE
                pending = []

        if pending:
            _copy_batch(pool, chunk_bucket, flex_bucket, pending)

    result = {
        'read': read,
        'read_batches': read // BATCH_SIZE,
        'flex': len(pending),
        'skipped_nova': skipped
    }
    logger.info('chunk2read complete: %s', result)
    return result
