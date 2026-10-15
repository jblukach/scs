# AWS Security Specialty Study Kit

An AWS CDK project that collects the official AWS documentation PDFs relevant to the **AWS Certified Security - Specialty (SCS-C03)** exam.

The stack creates private S3 buckets and six Lambda functions. The `scs-download` function is invoked manually to download the PDFs in `download/download.py` into the study bucket. Uploading a PDF to the PDF bucket triggers conversion to Markdown, and uploading one to the raw bucket triggers splitting into parts of up to 1,000 pages. The `text2chunk` function is invoked separately to chunk Markdown from the Markdown bucket; the deployed stack does not trigger it automatically when Markdown is created. The manually invoked `chunk2read` function stages chunks without existing Nova results for inference.

## Overview

This repository turns the official AWS documentation set for the AWS Certified Security - Specialty exam into a simple, repeatable S3-and-Lambda pipeline. The workflow is intentionally small:

1. Manually invoke the downloader to fetch the PDFs listed in `download/download.py` into the study bucket.
2. Upload source PDFs to the PDF bucket to trigger Markdown conversion.
3. Upload large source PDFs to the raw bucket to trigger splitting into numbered parts. This is an independent path; the split bucket does not trigger another Lambda.
4. Manually invoke the chunker to process Markdown in the Markdown bucket into section-aware, size-limited fragments for summarization and retrieval.
5. Manually invoke `chunk2read` to copy chunks absent from the Nova bucket to the read bucket in complete groups of 100, with the remaining 0-99 files copied to FLEX. Both paths save successful edits in the Nova bucket.

The implementation is centered on the AWS CDK stack in `scs/scs_stack.py`, with source handlers kept under `download/`, `pdf2md/`, `raw2split/`, `text2chunk/`, `chunk2read/`, and `read2nova/`.

## What it deploys

| Resource | Configuration |
| --- | --- |
| S3 bucket | `scs-use2-lukach-io`, S3-managed encryption, public access blocked, SSL required |
| Lambda function | `scs-download`, Python 3.13, ARM64, 15-minute timeout, 1 GiB memory |
| PDF bucket | `pdf-use2-lukach-io`, private S3 bucket for manually uploaded PDFs |
| Markdown bucket | `md-use2-lukach-io`, private S3 bucket for converted Markdown |
| Container Lambda | `pdf2md`, Python 3.13 image with `pymupdf4llm`, x86_64, 15-minute timeout, 4 GiB memory |
| Raw bucket | `raw-use2-lukach-io`, private S3 bucket for large PDFs awaiting a split |
| Split bucket | `split-use2-lukach-io`, private S3 bucket for the split PDF parts |
| Container Lambda | `raw2split`, Python 3.13 image with `pymupdf`, x86_64, 15-minute timeout, 4 GiB memory |
| Chunk bucket | `chunk-use2-lukach-io`, private S3 bucket for the Markdown chunks |
| Lambda function | `text2chunk`, Python 3.13, ARM64, 15-minute timeout, 3,008 MiB memory |
| Lambda function | `chunk2read`, ZIP-based Python 3.13, ARM64, 15-minute timeout, 1 GiB memory, reserved concurrency 1, manual invocation only |
| Read bucket | `read-use2-lukach-io`, private, encrypted, no versioning, retained on stack deletion |
| FLEX bucket | `flex-use2-lukach-io`, private, encrypted, no versioning, automatically processes small test sets with FLEX |
| Nova bucket | `nova-use2-lukach-io`, private, encrypted, no versioning, retained on stack deletion; contains only edited `.md` results |
| Batch bucket | `batch-use2-lukach-io`, private, encrypted, no versioning, retained; holds all internal working files (prepared inputs, batch job inputs, raw outputs, manifests) |
| SQS queue | `read2nova`, encrypted, 90-minute visibility timeout, 14-day retention |
| SQS DLQ | `read2nova-dlq`, encrypted, receives messages after five unsuccessful receives, 14-day retention |
| FLEX queue/DLQ | `flex2nova` and `flex2nova-dlq`, encrypted, one message per invocation, five receives before DLQ, 14-day retention, 90-minute visibility |
| Workflow failure queue | `read2nova-workflow-dlq`, retains failed asynchronous Lambda invocations and EventBridge deliveries for 14 days |
| Lambda function | `read2nova`, Python 3.13, ARM64, bundled AWS SDK, 15-minute timeout, 1 GiB memory, reserved concurrency 1 |
| DynamoDB table | `read2nova-state`, durable upload-event progress, active batch ownership, status index, and automatic FLEX quota reservations; on-demand billing |
| Bedrock service role | Scoped S3 input/output artifact access and Nova US inference-profile permissions |
| EventBridge | Five-minute dispatch/reconciliation schedule and batch terminal-state notifications |
| CloudWatch alarms | Batch/FLEX DLQs and queue age, workflow failure queue, and failed chunks |
| CloudWatch Logs | One-month retention for all six functions, including `/aws/lambda/chunk2read` and `/aws/lambda/read2nova` |

The original six buckets and their contents are configured for removal when the stack is destroyed. The read/FLEX/Nova buckets, all five Nova queues, and state table are retained so source objects, results, and pending work are not destroyed. No stack-managed bucket has versioning enabled. Overwriting an object replaces it without retaining an older version. Downloaded objects are replaced when the downloader runs again.

## Prerequisites

- AWS credentials configured for an account where you can deploy CDK resources
- AWS CDK v2 and Python 3.13+
- Node.js, required by the AWS CDK CLI
- Docker, running locally for the CDK container-image build
- An existing `packages-use2-lukach-io` bucket in the deployment account and `us-east-2` region, containing `requests.zip`
- Amazon Bedrock access to `us.amazon.nova-2-lite-v1:0`, including the destination regions in its US cross-region inference profile
- Nova batch-job capacity available in the account (defaults allocate two active jobs to this pipeline)
- On-demand Nova capacity for automatic processing of files copied to the FLEX bucket

The Lambda layer expects `requests.zip` to contain the `requests` dependency and to be compatible with Python 3.13 on ARM64.

## Deploy

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cdk bootstrap aws://ACCOUNT/us-east-2 --qualifier lukach
cdk deploy --profile scs
```

Replace `ACCOUNT` with the AWS account ID used for deployment. The stack is pinned to `us-east-2` and uses the CDK asset qualifier `lukach`, so the bootstrap environment must use that same qualifier. Deployment does not download or convert documents: the downloader, chunker, and `chunk2read` are manually invoked, while PDF conversion and splitting start only after an object is uploaded to their respective input buckets.

## Download the documents

Invoke the Lambda after deployment:

```bash
aws lambda invoke \
  --function-name scs-download \
  --region us-east-2 \
  response.json

cat response.json
```

The response includes the destination bucket, the number of successful downloads, and any URLs that failed:

```json
{
  "bucket": "scs-use2-lukach-io",
  "downloaded": 70,
  "failed": []
}
```

List or download the resulting files with the AWS CLI:

```bash
aws s3 ls s3://scs-use2-lukach-io/ --recursive
aws s3 sync s3://scs-use2-lukach-io/ ./pdfs
```

## Convert a PDF to Markdown

Upload a PDF to the input bucket to trigger conversion:

```bash
aws s3 cp ./input.pdf s3://pdf-use2-lukach-io/guides/input.pdf --region us-east-2
aws s3 cp s3://md-use2-lukach-io/guides/input.md ./input.md --region us-east-2
```

The Lambda writes the converted Markdown under the same folder path, replacing the `.pdf` extension with `.md`. Other uploaded file types are ignored. Existing Markdown at that key is overwritten if the PDF is uploaded again. The PDF and Markdown buckets are deleted with their contents when the stack is destroyed.

## Split a large PDF

Upload a PDF to the raw bucket to trigger `raw2split`:

```bash
aws s3 cp ./large.pdf s3://raw-use2-lukach-io/guides/large.pdf --region us-east-2
aws s3 ls s3://split-use2-lukach-io/ --region us-east-2
```

The Lambda splits the document into parts of 1,000 pages at most and writes them to the root of the split bucket, dropping any folder prefix. Each part keeps the source file name with a four-digit suffix, such as `large-0001.pdf` and `large-0002.pdf`, so sorting by name preserves the original page order. Documents of 1,000 pages or fewer still produce a single `-0001.pdf` part. Non-PDF uploads are ignored, and identically named PDFs in different raw folders overwrite each other in the split bucket.

## Chunk the Markdown

`text2chunk` is not wired to an S3 notification in this stack. Invoke it without a payload to scan and process every `.md` object already in the Markdown bucket, with up to eight files processed concurrently:

```bash
aws lambda invoke \
  --function-name text2chunk \
  --region us-east-2 \
  response.json

aws s3 ls s3://chunk-use2-lukach-io/ --region us-east-2
```

The Lambda walks the Markdown at `# ` and `## ` headings and packs content into chunks up to 15,000 characters, roughly 3,000 words. Short sections are packed together rather than written out as their own tiny objects. A section larger than the limit is broken down at `### ` and deeper headings, then paragraphs and lines; oversized content that still cannot be split at those boundaries is split by character count. Continuation chunks repeat the section's first heading with `(continued)` appended. Contiguous Markdown table rows and fenced code blocks are kept together when they fit within the limit; an oversized table or code block may be split as a last resort.

Every chunk opens with a blockquote preamble naming the source object and chunk position; document title and section are included when available. This keeps each chunk self-describing for a downstream summarizer that sees it in isolation:

```markdown
> Source: guides/amazon-guardduty-0001.md
> Document: Amazon GuardDuty User Guide
> Section: Managing findings
> Chunk 47 of 132
```

Chunks are written to the root of the chunk bucket with no folders. Each chunk keeps the source file name with a four-digit suffix, such as `large-0001-0001.md`, so a Markdown file that already carries a split suffix gains a second one and sorting by name still preserves the original order. Non-Markdown objects are ignored, and identically named Markdown files in different folders overwrite each other in the chunk bucket.

Each file is downloaded to a private directory under `/tmp` that is removed after its chunks are uploaded, so the function's scratch space stays empty between files.

## Stage unfinished chunks with chunk2read

Invoke the ZIP-based Lambda manually; it has no S3 trigger or schedule and needs no Docker image or extra layer:

```bash
aws lambda invoke --function-name chunk2read \
  --cli-binary-format raw-in-base64-out --payload '{}' \
  --region us-east-2 --profile scs response.json

cat response.json
```

The function paginates all keys in `nova-use2-lukach-io` first, then scans all objects in `chunk-use2-lukach-io`. Matching keys are excluded regardless of content or file extension. Each full group of **exactly 100 eligible files** is copied to `read-use2-lukach-io`; the final **0-99 files** go to `flex-use2-lukach-io`. For example, 250 eligible files produce two read groups and 50 FLEX copies. Keys, folder paths, content, and metadata are preserved, and source chunks are not deleted. All file types are copied, although the downstream inference notifications process only lowercase `.md` keys.

The response reports counts, for example `{"read":200,"read_batches":2,"flex":50,"skipped_nova":30}`. Read/FLEX copies immediately trigger the existing paid inference pipeline. These are copy groups, not forced Bedrock job boundaries: the existing dispatcher still assembles 100-500 records per job according to `NovaBatchSize`.

Nova exclusion uses the key listing at the start of the invocation. Run against a stable chunk set and wait for earlier inference runs to finish before invoking again; pending read/FLEX work without a Nova result is eligible to be copied again. Reserved concurrency prevents overlapping `chunk2read` executions, not other writers. S3 copies are not transactional: an error or the 15-minute Lambda timeout fails the invocation but leaves any completed copies in place, potentially including an incomplete read group. Inspect the Lambda error and pending inference work before rerunning; there is no automatic rollback or retry workflow.

## Edit chunks with Nova 2 Lite batch inference

After deployment, copy the existing small chunks into the read bucket:

```bash
aws s3 cp ./selected-chunks/ s3://read-use2-lukach-io/guides/ \
  --recursive --exclude "*" --include "*.md" --region us-east-2 --profile scs

aws s3 ls s3://nova-use2-lukach-io/guides/ --recursive \
  --region us-east-2 --profile scs
```

You can also copy directly from `chunk-use2-lukach-io`, using the same recursive include/exclude filters. Copying is intentional: the chunk bucket does not automatically incur inference charges. Only object-created events for lowercase `.md` keys enqueue registration, including S3 copies and completed multipart uploads. Objects that existed before notification setup must be copied again to create an event.

`read2nova` reads the source with an `If-Match` condition against the upload event's ETag, prepares a Converse JSON record under `batch-use2-lukach-io/prepared/`, and registers a hash of the bucket, key, event sequencer, and ETag in DynamoDB. SQS is acknowledged only after this durable registration; pending batch work then survives beyond SQS's 14-day retention. Duplicate deliveries of the same event do not reset progress or cause another inference. Reuploading even identical content creates a new event sequencer and is processed again.

There is no S3 versioning. If different content replaces a source before registration, its old notification fails the ETag condition and follows SQS/DLQ recovery rather than editing the wrong text. Once prepared, retries use the saved JSON input even if the source subsequently changes. ETags are content validators, not historical upload identifiers: identical replacement content can still satisfy an older event's ETag.

A five-minute dispatcher assembles 100-500 records, capped at 64 MiB per input file, into `batch-use2-lukach-io/jobs/JOB_ID/input.jsonl` and submits an asynchronous Bedrock batch job. Defaults are **500 records/job and two active jobs**. Batch capacity is separate from synchronous RPM/TPM budgets; change `NovaBatchSize` or `NovaActiveJobs` at deployment if appropriate. The worker's reserved concurrency stays at one to serialize durable ownership, but Bedrock runs the two submitted jobs independently.

**The read bucket is batch-only, regardless of folder name.** There is no `tests/` exception or manual FLEX invocation for read sources. AWS requires at least 100 records per Nova batch job, so a final tail smaller than 100 stays pending until enough new chunks arrive. Nothing in the read bucket automatically falls back to FLEX, and no dummy prompts or paid padding are submitted.

Bedrock writes raw output under `batch-use2-lukach-io/jobs/JOB_ID/raw/`. Terminal-job EventBridge notifications trigger collection, with scheduled reconciliation as a fallback for missed events. Results are matched by `recordId`, not output order, validated, and saved as individual Markdown files under the **same key and folder path as the source**. A per-job manifest is saved under `batch-use2-lukach-io/jobs/JOB_ID/manifest.json`. All working files stay in the batch bucket, so the read and FLEX buckets contain only your sources and the Nova bucket contains only edited `.md` files. Do not delete objects from the batch bucket while jobs are active; if raw results disappear, the collector marks those records `FAILED` with a message saying the batch output may have been deleted, and they must be retried (and billed) again.

The Lambda does not wait for batch inference. Interrupted preparation uses the same persisted job token when resubmitted, and interrupted collection resumes from durable chunk statuses. Submitted jobs have a 48-hour timeout; actual completion depends on Bedrock capacity. Batch inference is **not FLEX**, and its pricing is separate.

The prompt condenses each chunk into general AWS certification study notes of roughly 30-50% of the source length, not tied to a single exam. It explains what each service or feature does, why it matters, how it works, and when to use it, and keeps configuration options, defaults, limits, security, reliability, performance, cost, trade-offs, and pitfalls stated in the source. It condenses lengthy descriptions and removes console steps, marketing, and boilerplate. Every chunk follows the same structure so chapters merge consistently: the source provenance lines copied exactly, one `###` topic heading (without "(continued)"), a 2-4 sentence overview, then **Key concepts**, **Configuration, defaults, and limits**, and **When to use and trade-offs** (the last two omitted when the source has nothing for them), optional `> **Definition:**` or `> **Best Practice:**` callouts, and exactly one closing `> **Key Takeaway:**`. `####` is used only for distinct sub-topics. The prompt includes a short worked example (Amazon SQS visibility timeout) that shows the expected depth and is explicitly not to be copied. Chunks with no substantive technical content produce only the provenance lines and `> **Study Relevance:** None in this section.` so they can be skipped during chapter merging. It forbids facts not stated in the source, preserves exact names, values, and provenance, requires academic prose, and requests raw GFM with headings starting at H3. Inference uses `temperature` 0 for consistent structure across chunks and between batch and FLEX. The prompt is captured when a file is registered, so files registered before a prompt change keep the earlier prompt on retry; copy them again to use the new prompt. An unambiguous whole-response `markdown`, `md`, or unlabeled fence is removed before validation, preserving the enclosed content and legitimate inner code blocks. Incomplete, mismatched, or ambiguous wrappers remain errors. Empty responses, incomplete stop reasons, H1/H2 headings, and unclosed code fences are rejected. This normalization applies to both batch and FLEX and avoids retrying solely for a removable wrapper. Validation cannot guarantee factual accuracy; review representative edits before running the full collection. When an accepted output is larger than 80% of its source in UTF-8 bytes, the Lambda logs a `LowCondensation id=... key=... ratio=...` warning but still saves the output. The `Read2Nova/LowCondensation` CloudWatch metric counts these warnings (no alarm). Find them with the CloudWatch Logs Insights query `fields @timestamp, @message | filter @message like /LowCondensation/ | sort @timestamp desc`. Frequent warnings indicate the prompt or chunk content needs review.

### Automatically test a small set with FLEX

Copy one or more Markdown files into `flex-use2-lukach-io`. Copying is the only action needed to start processing:

```bash
aws s3 cp ./test-chunks/ s3://flex-use2-lukach-io/tests/ \
  --recursive --exclude "*" --include "*.md" --region us-east-2 --profile scs

aws s3 ls s3://nova-use2-lukach-io/tests/ --recursive \
  --region us-east-2 --profile scs

aws s3 cp s3://nova-use2-lukach-io/tests/sample.md ./sample-edited.md \
  --region us-east-2 --profile scs
```

The `tests/` folder is just an example; every lowercase `.md` key in the FLEX bucket uses FLEX, regardless of prefix. S3 events enter the separate `flex2nova` queue. The worker conditionally reads the source using the event's ETag, calls Converse with `serviceTier={"type":"flex"}`, validates the edit, and writes it under the **same key in the Nova bucket**. Processing is asynchronous from the upload, so the output may take several minutes to appear. No CLI Lambda invocation or minimum file count is required.

FLEX uses the same prompt and output validation as batch, but it is a separate billable mode and does not certify batch-job IAM or runtime behavior. Run a representative batch of at least 100 files before the full collection. Use different source keys for test and production outputs: uploading the same key in both buckets writes to the same Nova key, and whichever finishes last replaces the output. Previous outputs are not retained.

Like `text2chunk`, this is a ZIP-based Python 3.13 ARM64 Lambda using the runtime's bundled `boto3`, with no Docker or SDK layer. That SDK must support `CreateModelInvocationJob.modelInvocationType="Converse"` and FLEX's `serviceTier` field. Unsupported fields fail visibly; there is no silent Standard-tier fallback.

### Limits, failures, and recovery

[Nova 2 Lite](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html) has a **1M-token context window and approximately 64K maximum output**, not 1M output tokens. `NovaMaxOutputTokens` defaults to 8000 and supports up to 64000. Condensed output for a 15,000-character chunk needs far fewer tokens, and the lower limit reduces FLEX quota reservations and bounds runaway responses; a response that reaches the limit fails as incomplete. This pipeline accepts at most 100,000 UTF-8 bytes per source chunk, keeping prepared batches well below the 1 GB input-file limit even with JSON escaping. The existing 15,000-character chunks fit comfortably. Larger sources fail registration for rechunking.

Automatic FLEX calls reserve UTF-8 byte counts plus prompt/framing overhead and the maximum output tokens against a persistent rolling-minute ledger. Defaults are `NovaRequestsPerMinute=10` and `NovaTokensPerMinute=100000`; these parameters **do not limit batch jobs**. They must fit the account's available on-demand quota, shared with other callers. FLEX uses a 780-second read timeout without SDK inference retries. Waiting is billable Lambda time, and SQS retries after timeouts may cause duplicate inference charges.

**Do not increase Lambda reserved concurrency or run another worker against this table.** The single coordinator makes batch ownership and test quota reservations safe. Increase `NovaActiveJobs` instead, within the account's remaining batch-job quota.

Read-source preparation failures retry through SQS and reach `read2nova-dlq` after five unsuccessful receives. FLEX preparation, inference, validation, or persistence failures retry through `flex2nova` and reach `flex2nova-dlq` after five unsuccessful receives. Successful FLEX upload events are tracked as DONE so duplicate notifications do not invoke Nova again. Resolve failures before the 14-day queue retention expires. Redrive them to their original queue:

```bash
DLQ_ARN=$(aws sqs get-queue-attributes \
  --queue-url "$(aws sqs get-queue-url --queue-name read2nova-dlq \
    --region us-east-2 --profile scs --query QueueUrl --output text)" \
  --attribute-names QueueArn --region us-east-2 --profile scs \
  --query Attributes.QueueArn --output text)

aws sqs start-message-move-task --source-arn "$DLQ_ARN" \
  --max-number-of-messages-per-second 1 --region us-east-2 --profile scs
```

For FLEX redrive, use the same commands with `flex2nova-dlq` instead of `read2nova-dlq`; the message-move task returns the original source notifications to `flex2nova`. Event sequencers and ETags are preserved, and a failed FLEX chunk never becomes a batch chunk. Redrive cannot recover overwritten content that was never prepared; upload the intended file again to create a new event instead.

The separate `read2nova-workflow-dlq` contains failed asynchronous Lambda invocations and failed EventBridge deliveries, **not S3 source notifications**. Inspect the error, fix the cause, and invoke `{"action":"dispatch"}` to reconcile again. Do not redrive those envelopes into either source queue.

Model record errors, invalid Markdown, and missing terminal-job results are logged as `ChunkFailed` and retained as **FAILED** chunks in DynamoDB. They do not automatically incur unlimited paid retries. Find failed IDs and details:

```bash
aws dynamodb query --table-name read2nova-state --index-name by-status \
  --key-condition-expression "#s = :s" \
  --expression-attribute-names '{"#s":"status"}' \
  --expression-attribute-values '{":s":{"S":"FAILED"}}' \
  --region us-east-2 --profile scs

aws dynamodb get-item --table-name read2nova-state \
  --key '{"id":{"S":"FAILED_SOURCE_HASH"}}' --consistent-read \
  --region us-east-2 --profile scs

aws lambda invoke --function-name read2nova \
  --cli-binary-format raw-in-base64-out \
  --payload '{"action":"retry","ids":["FAILED_SOURCE_HASH"]}' \
  --region us-east-2 --profile scs response.json
```

Retry accepts up to 500 failed **read-bucket** IDs whose jobs have finished collection, returning them to batch pending. FLEX IDs are rejected by this action; use FLEX-DLQ redrive instead. Retry original IDs rather than copying every successful source again. Failed preparation needs source-DLQ recovery instead; no chunk exists yet.

CloudWatch alarms cover both source DLQs, the workflow failure queue, batch/FLEX messages older than one day, and model/validation failures. They are visible in CloudWatch but have no email/SNS actions configured. Monitor these before large runs; the durable manifest protects registered batch work, not notifications that expire before registration or unfinished FLEX messages. All five queues retain messages for only 14 days. FLEX and batch coordination share one Lambda execution slot, so long FLEX waits delay batch registration/dispatch; keep the FLEX bucket for small test sets.

To pause new batch submissions without discarding pending work:

```bash
aws lambda invoke --function-name read2nova \
  --cli-binary-format raw-in-base64-out --payload '{"action":"pause"}' \
  --region us-east-2 --profile scs response.json
```

Use `{"action":"resume"}` to resume. Already submitted jobs continue and their results are collected while paused; automatic FLEX uploads continue independently of this batch pause. Pausing is not a spending cap or cancellation of running jobs.

Use immutable source keys and avoid overwriting a key while work is pending. Events and jobs can finish out of order, so an older prepared upload can otherwise overwrite a newer result. Neither source nor output history is retained by S3. The batch bucket holds internal artifacts only (prepared inputs for both read and FLEX sources, batch inputs, raw outputs, and manifests); never upload source chunks there, as it has no event notifications. Once no jobs are active and the state table shows the relevant chunks `DONE`, you may empty the batch bucket; failed chunks then must be copied again rather than retried. Prepared inputs, raw artifacts, and state are retained without automatic lifecycle deletion, so include their storage in cost planning.

## Project layout

```text
.
├── app.py                 # CDK application entry point
├── cdk.json               # CDK CLI configuration
├── download/download.py   # Lambda handler and document manifest
├── pdf2md/Dockerfile      # Container Lambda image with pymupdf4llm
├── pdf2md/pdf2md.py      # S3 event handler and PDF conversion
├── raw2split/Dockerfile   # Container Lambda image with pymupdf
├── raw2split/raw2split.py # S3 event handler and PDF splitting
├── text2chunk/text2chunk.py # Markdown chunking handler
├── chunk2read/chunk2read.py # Manual Nova exclusion and read/FLEX copy routing
├── read2nova/read2nova.py # Registration, batch jobs/results, and automatic FLEX uploads
├── scs/scs_stack.py       # Infrastructure definition
├── tests/test_pdf2md.py  # Conversion event test
├── tests/test_raw2split.py # Split event test
├── tests/test_text2chunk.py # Chunking test
├── tests/test_read2nova.py # Batch recovery and automatic FLEX routing tests
├── tests/test_chunk2read.py # Exact copy groups, Nova exclusion, pagination, and failures
├── tests/test_nova_stack.py # Nova infrastructure assertions
└── requirements.txt       # Python dependencies
```

## Study guide

The manifest contains the exam guide plus the following official AWS documentation. Links open the PDFs directly from AWS and match the current manifest in `download/download.py`.

<details>
<summary><strong>Exam guide</strong></summary>

- [AWS Certified Security - Specialty (SCS-C03) exam guide](https://docs.aws.amazon.com/pdfs/aws-certification/latest/security-specialty-03/security-specialty-03.pdf)

</details>

<details>
<summary><strong>Analytics</strong></summary>

- [Amazon Athena](https://docs.aws.amazon.com/pdfs/athena/latest/ug/athena-ug.pdf)
- [Amazon OpenSearch Service](https://docs.aws.amazon.com/pdfs/opensearch-service/latest/developerguide/opensearch-service-dg.pdf)

</details>

<details>
<summary><strong>Application Integration</strong></summary>

- [Amazon SNS](https://docs.aws.amazon.com/pdfs/sns/latest/dg/sns-dg.pdf)
- [AWS Step Functions](https://docs.aws.amazon.com/pdfs/step-functions/latest/dg/step-functions-dg.pdf)

</details>

<details>
<summary><strong>Compute</strong></summary>

- [Amazon API Gateway](https://docs.aws.amazon.com/pdfs/apigateway/latest/developerguide/apigateway-dg.pdf)
- [Amazon EC2](https://docs.aws.amazon.com/pdfs/AWSEC2/latest/UserGuide/ec2-ug.pdf)
- [EC2 Image Builder](https://docs.aws.amazon.com/pdfs/imagebuilder/latest/userguide/imagebuilder-ug.pdf)
- [Amazon EKS](https://docs.aws.amazon.com/pdfs/eks/latest/userguide/eks-ug.pdf)
- [Amazon EMR](https://docs.aws.amazon.com/pdfs/emr/latest/ManagementGuide/emr-mgmt.pdf)
- [AWS Lambda](https://docs.aws.amazon.com/pdfs/lambda/latest/dg/lambda-dg.pdf)

</details>

<details>
<summary><strong>Developer Tools</strong></summary>

- [AWS Fault Injection Service](https://docs.aws.amazon.com/pdfs/fis/latest/userguide/fis-guide.pdf)

</details>

<details>
<summary><strong>Internet of Things</strong></summary>

- [AWS IoT Core](https://docs.aws.amazon.com/pdfs/iot/latest/developerguide/iot-dg.pdf)

</details>

<details>
<summary><strong>Machine Learning</strong></summary>

- [Amazon Bedrock](https://docs.aws.amazon.com/pdfs/bedrock/latest/userguide/bedrock-ug.pdf)
- [Amazon CodeGuru Profiler](https://docs.aws.amazon.com/pdfs/codeguru/latest/profiler-ug/profiler-ug.pdf)
- [Amazon CodeGuru Reviewer](https://docs.aws.amazon.com/pdfs/codeguru/latest/reviewer-ug/reviewer-ug.pdf)
- [Amazon Q Business](https://docs.aws.amazon.com/pdfs/amazonq/latest/qbusiness-ug/qbusiness-ug.pdf)
- [Amazon Q Developer](https://docs.aws.amazon.com/pdfs/amazonq/latest/qdeveloper-ug/amazonq-developer-ug.pdf)
- [Amazon SageMaker AI](https://docs.aws.amazon.com/pdfs/sagemaker/latest/dg/sagemaker-dg.pdf)

</details>

<details>
<summary><strong>Management and Governance</strong></summary>

- [AWS CloudFormation](https://docs.aws.amazon.com/pdfs/AWSCloudFormation/latest/UserGuide/cfn-ug.pdf)
- [AWS CloudTrail](https://docs.aws.amazon.com/pdfs/awscloudtrail/latest/userguide/awscloudtrail-ug.pdf)
- [Amazon CloudWatch monitoring](https://docs.aws.amazon.com/pdfs/AmazonCloudWatch/latest/monitoring/acw-ug.pdf)
- [Amazon CloudWatch Logs](https://docs.aws.amazon.com/pdfs/AmazonCloudWatch/latest/logs/cwl-ug.pdf)
- [Amazon EventBridge](https://docs.aws.amazon.com/pdfs/eventbridge/latest/userguide/user-guide.pdf)
- [AWS Config](https://docs.aws.amazon.com/pdfs/config/latest/developerguide/config-dg.pdf)
- [AWS Control Tower](https://docs.aws.amazon.com/pdfs/controltower/latest/userguide/controltower-ug.pdf)
- [Amazon Managed Grafana](https://docs.aws.amazon.com/pdfs/grafana/latest/userguide/service-guide.pdf.pdf)
- [AWS Organizations](https://docs.aws.amazon.com/pdfs/organizations/latest/userguide/organizations-userguide.pdf)
- [AWS Resilience Hub](https://docs.aws.amazon.com/pdfs/resilience-hub/latest/userguide/resilience-hub-guide.pdf)
- [AWS Resource Explorer](https://docs.aws.amazon.com/pdfs/resource-explorer/latest/userguide/resource_explorer_ug.pdf)
- [AWS Service Catalog](https://docs.aws.amazon.com/pdfs/servicecatalog/latest/adminguide/service-catalog-ag.pdf)
- [AWS Systems Manager](https://docs.aws.amazon.com/pdfs/systems-manager/latest/userguide/systems-manager-ug.pdf)
- [AWS Trusted Advisor](https://docs.aws.amazon.com/pdfs/awssupport/latest/user/support-ug.pdf)
- [AWS User Notifications](https://docs.aws.amazon.com/pdfs/notifications/latest/userguide/notifications-guide.pdf.pdf)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/pdfs/wellarchitected/latest/userguide/wellarchitected-ug.pdf)

</details>

<details>
<summary><strong>Networking and Content Delivery</strong></summary>

- [Amazon Application Recovery Controller](https://docs.aws.amazon.com/pdfs/r53recovery/latest/dg/r53-recovery-guide.pdf.pdf)
- [Amazon VPC](https://docs.aws.amazon.com/pdfs/vpc/latest/userguide/vpc-ug.pdf)
- [AWS Site-to-Site VPN](https://docs.aws.amazon.com/pdfs/vpn/latest/s2svpn/s2s-vpn-user-guide.pdf)
- [AWS Verified Access](https://docs.aws.amazon.com/pdfs/verified-access/latest/ug/verified-access-ug.pdf)
- [AWS Client VPN](https://docs.aws.amazon.com/pdfs/vpn/latest/clientvpn-user/client-vpn-user-guide.pdf)
- [Amazon CloudFront](https://docs.aws.amazon.com/pdfs/AmazonCloudFront/latest/DeveloperGuide/AmazonCloudFront_DevGuide.pdf)
- [Amazon Verified Permissions](https://docs.aws.amazon.com/pdfs/verifiedpermissions/latest/userguide/amazon-verified-permissions-user-guide.pdf)
- [Amazon Route 53](https://docs.aws.amazon.com/pdfs/Route53/latest/DeveloperGuide/route53-dg.pdf)
- [AWS Direct Connect](https://docs.aws.amazon.com/pdfs/directconnect/latest/UserGuide/dc-ug.pdf)
- [Elastic Load Balancing](https://docs.aws.amazon.com/pdfs/elasticloadbalancing/latest/userguide/elb-ug.pdf)
- [AWS Transit Gateway](https://docs.aws.amazon.com/pdfs/vpc/latest/tgw/vpc-tgw.pdf)

</details>

<details>
<summary><strong>Security</strong></summary>

- [AWS Artifact](https://docs.aws.amazon.com/pdfs/artifact/latest/ug/artifact-ug.pdf)
- [AWS Audit Manager](https://docs.aws.amazon.com/pdfs/audit-manager/latest/userguide/audit-manager-ug.pdf)
- [AWS Certificate Manager](https://docs.aws.amazon.com/pdfs/acm/latest/userguide/acm-ug.pdf)
- [AWS CloudHSM](https://docs.aws.amazon.com/pdfs/cloudhsm/latest/userguide/cloudhsm-user-guide.pdf)
- [Amazon Cognito](https://docs.aws.amazon.com/pdfs/cognito/latest/developerguide/cognito-dg.pdf)
- [Amazon Detective](https://docs.aws.amazon.com/pdfs/detective/latest/userguide/detective-ug.pdf)
- [AWS Directory Service](https://docs.aws.amazon.com/pdfs/directoryservice/latest/admin-guide/directoryservice-admin-guide.pdf)
- [AWS Firewall Manager](https://docs.aws.amazon.com/pdfs/waf/latest/developerguide/waf-dg.pdf)
- [Amazon GuardDuty](https://docs.aws.amazon.com/pdfs/guardduty/latest/ug/guardduty-ug.pdf)
- [AWS Identity and Access Management](https://docs.aws.amazon.com/pdfs/IAM/latest/UserGuide/iam-ug.pdf)
- [AWS IAM Identity Center](https://docs.aws.amazon.com/pdfs/singlesignon/latest/userguide/sso-ug.pdf)
- [Amazon Inspector](https://docs.aws.amazon.com/pdfs/inspector/latest/user/inspector-guide.pdf)
- [AWS Key Management Service](https://docs.aws.amazon.com/pdfs/kms/latest/developerguide/kms-dg.pdf)
- [Amazon Macie](https://docs.aws.amazon.com/pdfs/macie/latest/user/macie-user-guide.pdf)
- [AWS Network Firewall](https://docs.aws.amazon.com/pdfs/network-firewall/latest/developerguide/network-firewall-developer-guide.pdf)
- [AWS Private Certificate Authority](https://docs.aws.amazon.com/pdfs/privateca/latest/userguide/privateca-ug.pdf)
- [AWS Secrets Manager](https://docs.aws.amazon.com/pdfs/secretsmanager/latest/userguide/secretsmanager-userguide.pdf)
- [AWS Security Hub](https://docs.aws.amazon.com/pdfs/securityhub/latest/userguide/securityhub.pdf)
- [Amazon Security Lake](https://docs.aws.amazon.com/pdfs/security-lake/latest/userguide/security-lake-userguide.pdf)

</details>

<details>
<summary><strong>Storage</strong></summary>

- [Amazon S3](https://docs.aws.amazon.com/pdfs/AmazonS3/latest/userguide/s3-userguide.pdf)
- [AWS Backup](https://docs.aws.amazon.com/pdfs/aws-backup/latest/devguide/AWSBackup-dg.pdf)
- [AWS DataSync](https://docs.aws.amazon.com/pdfs/datasync/latest/userguide/datasync-userguide.pdf)
- [Amazon EFS](https://docs.aws.amazon.com/pdfs/efs/latest/ug/efs-ug.pdf)
- [Amazon FSx for Lustre](https://docs.aws.amazon.com/pdfs/fsx/latest/FileCacheGuide/FileCacheGuide.pdf)

</details>

## Useful commands

```bash
cdk diff       # Review infrastructure changes
cdk synth      # Generate the CloudFormation template
cdk destroy    # Delete the stack; Nova pipeline data/queues/table are retained
```

The stack is intentionally focused on collecting documents. Edit the `pdfs` mapping of filename to URL in `download/download.py` to change the manifest.
