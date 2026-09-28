import os

import boto3


def handler(event, context):
    s3 = boto3.client('s3')
    source_bucket = os.environ['SOURCE_BUCKET']
    destination_bucket = os.environ['DESTINATION_BUCKET']
    copied = 0

    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=source_bucket):
        for item in page.get('Contents', []):
            key = item['Key']
            s3.copy(
                {'Bucket': source_bucket, 'Key': key},
                destination_bucket,
                key
            )
            copied += 1

    return {'source': source_bucket, 'destination': destination_bucket, 'copied': copied}