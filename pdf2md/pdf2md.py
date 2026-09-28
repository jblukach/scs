import os
from urllib.parse import unquote_plus

import boto3
import pymupdf4llm


def handler(event, context):
    s3 = boto3.client('s3')
    md_bucket = os.environ['MD_BUCKET']

    for record in event['Records']:
        source_bucket = record['s3']['bucket']['name']
        source_key = unquote_plus(record['s3']['object']['key'])
        if not source_key.lower().endswith('.pdf'):
            continue

        s3.download_file(source_bucket, source_key, '/tmp/input.pdf')
        markdown = pymupdf4llm.to_markdown('/tmp/input.pdf')
        s3.put_object(
            Bucket=md_bucket,
            Key=source_key[:-4] + '.md',
            Body=markdown.encode('utf-8'),
            ContentType='text/markdown; charset=utf-8'
        )