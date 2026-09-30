FROM public.ecr.aws/lambda/python:3.13

RUN pip install --no-cache-dir pymupdf

COPY raw2split.py ${LAMBDA_TASK_ROOT}/

CMD ["raw2split.handler"]
