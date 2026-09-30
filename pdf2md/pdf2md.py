import os
from urllib.parse import unquote_plus

import boto3
import pymupdf
import pymupdf4llm

s3 = boto3.client('s3')


def handler(event, context):
    md_bucket = os.environ['MD_BUCKET']

    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        if not key.lower().endswith('.pdf'):
            continue

        data = s3.get_object(Bucket = bucket, Key = key)['Body'].read()
        with pymupdf.open(stream = data, filetype = 'pdf') as doc:
            markdown = pymupdf4llm.to_markdown(doc, force_ocr = False)

        s3.put_object(
            Bucket = md_bucket,
            Key = key[:-4]+'.md',
            Body = markdown.encode('utf-8'),
            ContentType = 'text/markdown; charset=utf-8'
        )
        print('CONVERTED '+key)
