import os
import time
from urllib.parse import unquote_plus

import boto3
import pymupdf4llm

try:
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover - boto3 still provides this in Lambda
    class ClientError(Exception):
        pass


def _convert_pdf_in_chunks(local_path, chunk_size=25):
    try:
        import fitz
    except ImportError:
        return pymupdf4llm.to_markdown(local_path, force_ocr=False)

    doc = fitz.open(local_path)
    page_count = doc.page_count
    if page_count <= chunk_size:
        doc.close()
        return pymupdf4llm.to_markdown(local_path, force_ocr=False)

    markdown_parts = []
    for start in range(0, page_count, chunk_size):
        end = min(start + chunk_size, page_count)
        chunk_path = f'/tmp/chunk_{start + 1}_{end}.pdf'
        chunk_doc = fitz.open()
        chunk_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
        chunk_doc.save(chunk_path)
        chunk_doc.close()
        markdown = pymupdf4llm.to_markdown(chunk_path, force_ocr=False)
        if markdown.strip():
            markdown_parts.append(markdown)

    doc.close()
    return '\n\n'.join(markdown_parts)


def _convert_one_pdf(s3, source_bucket, source_key, md_bucket):
    local_path = '/tmp/input.pdf'
    started = time.perf_counter()
    print(f'pdf2md: starting conversion for bucket={source_bucket} key={source_key}')
    try:
        s3.download_file(source_bucket, source_key, local_path)
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') == '404':
            print(f'pdf2md: skipping missing object bucket={source_bucket} key={source_key}')
            return {'bucket': source_bucket, 'key': source_key, 'converted': False, 'reason': 'missing'}
        raise
    print(f'pdf2md: downloaded bucket={source_bucket} key={source_key}')
    markdown = _convert_pdf_in_chunks(local_path, chunk_size=25)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    print(f'pdf2md: converted bucket={source_bucket} key={source_key} elapsed_ms={elapsed_ms} bytes={len(markdown.encode("utf-8"))}')
    s3.put_object(
        Bucket=md_bucket,
        Key=source_key[:-4] + '.md',
        Body=markdown.encode('utf-8'),
        ContentType='text/markdown; charset=utf-8'
    )
    print(f'pdf2md: uploaded markdown for bucket={source_bucket} key={source_key} elapsed_ms={elapsed_ms}')
    return {'bucket': source_bucket, 'key': source_key, 'converted': True}


def handler(event, context):
    s3 = boto3.client('s3')
    md_bucket = os.environ['MD_BUCKET']

    for record in event.get('Records', []):
        source_bucket = record['s3']['bucket']['name']
        source_key = unquote_plus(record['s3']['object']['key'])
        if not source_key.lower().endswith('.pdf'):
            continue

        return _convert_one_pdf(s3, source_bucket, source_key, md_bucket)

    print('pdf2md: no PDF records found in event')
    return {'converted': 0}