FROM public.ecr.aws/lambda/python:3.13

RUN pip install --no-cache-dir pymupdf4llm

COPY pdf2md.py ${LAMBDA_TASK_ROOT}/

CMD ["pdf2md.handler"]