#!/usr/bin/env python3
import os

import aws_cdk as cdk

from scs.scs_stack import ScsStack

app = cdk.App()

ScsStack(
    app, 'ScsStack',
    env = cdk.Environment(
        account = os.getenv('CDK_DEFAULT_ACCOUNT'),
        region = 'us-east-2'
    ),
    synthesizer = cdk.DefaultStackSynthesizer(
        qualifier = 'lukach'
    )
)

cdk.Tags.of(app).add('Alias','scs')
cdk.Tags.of(app).add('GitHub','https://github.com/jblukach/scs')
cdk.Tags.of(app).add('Org','lukach.io')

app.synth()