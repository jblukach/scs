import os
from urllib.parse import unquote_plus

import boto3
import pymupdf

s3 = boto3.client('s3')

PAGES = 1000


def handler(event, context):
    split_bucket = os.environ['SPLIT_BUCKET']

    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        if not key.lower().endswith('.pdf'):
            continue

        data = s3.get_object(Bucket = bucket, Key = key)['Body'].read()
        base = os.path.basename(key)[:-4]

        with pymupdf.open(stream = data, filetype = 'pdf') as doc:
            for number, start in enumerate(range(0, doc.page_count, PAGES), start = 1):
                part = pymupdf.open()
                part.insert_pdf(doc, from_page = start, to_page = min(start+PAGES, doc.page_count)-1)
                body = part.tobytes(garbage = 4, deflate = True)
                part.close()

                part_key = base+'-'+str(number).zfill(4)+'.pdf'

                s3.put_object(
                    Bucket = split_bucket,
                    Key = part_key,
                    Body = body,
                    ContentType = 'application/pdf'
                )
                print('SPLIT '+key+' -> '+part_key)
