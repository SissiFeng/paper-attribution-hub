"""Shared Slack configuration, author registry and feedback; tokens stay in SSM."""
from __future__ import annotations

import json
import os
import time
from functools import lru_cache


@lru_cache(maxsize=1)
def session():
    import boto3
    return boto3.Session()


@lru_cache(maxsize=8)
def client(name):
    return session().client(name)


@lru_cache(maxsize=1)
def table():
    return session().resource('dynamodb').Table(os.environ['SLACK_TABLE'])


def get(key):
    item = table().get_item(Key={'pk': key}, ConsistentRead=True).get('Item', {})
    return json.loads(item.get('payload', '{}'))


def put(key, value, *, only_new=False):
    args = {'Item': {'pk': key, 'payload': json.dumps(value, ensure_ascii=False), 'version': time.time_ns()}}
    if only_new:
        args['ConditionExpression'] = 'attribute_not_exists(pk)'
    table().put_item(**args)


def change(key, edit):
    """Optimistic transaction: edit can validate the freshly read state."""
    from botocore.exceptions import ClientError
    for _ in range(4):
        item = table().get_item(Key={'pk': key}, ConsistentRead=True).get('Item')
        value = json.loads(item['payload']) if item else {}
        edit(value)
        args = {'Item': {'pk': key, 'payload': json.dumps(value, ensure_ascii=False), 'version': time.time_ns()}}
        if item and 'expires' in item:
            args['Item']['expires'] = item['expires']
        if item:
            args.update(ConditionExpression='#v = :v', ExpressionAttributeNames={'#v': 'version'},
                        ExpressionAttributeValues={':v': item['version']})
        else:
            args['ConditionExpression'] = 'attribute_not_exists(pk)'
        try:
            table().put_item(**args)
            return value
        except ClientError as exc:
            if exc.response['Error']['Code'] != 'ConditionalCheckFailedException':
                raise
    raise RuntimeError('Configuration changed concurrently; try again')


def authors():
    from boto3.dynamodb.conditions import Attr
    rows, kwargs = [], {'FilterExpression': Attr('pk').begins_with('author:')}
    while True:
        page = table().scan(**kwargs)
        rows.extend(json.loads(i['payload']) for i in page['Items'])
        if not page.get('LastEvaluatedKey'):
            return sorted(rows, key=lambda r: r['name'].casefold())
        kwargs['ExclusiveStartKey'] = page['LastEvaluatedKey']


def credentials():
    from botocore.exceptions import ClientError
    try:
        raw = client('ssm').get_parameter(Name=os.environ['SLACK_CONFIG_PARAMETER'], WithDecryption=True)
        return json.loads(raw['Parameter']['Value'])
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ParameterNotFound':
            return {}
        raise


def configure_openalex():
    """Optional independent key: collection works before Slack is installed."""
    from botocore.exceptions import ClientError
    parameter = os.environ.get('OPENALEX_PARAMETER')
    if not parameter:
        return
    try:
        raw = client('ssm').get_parameter(Name=parameter, WithDecryption=True)
        os.environ['OPENALEX_API_KEY'] = raw['Parameter']['Value']
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'ParameterNotFound':
            raise


def configure_jev():
    """Optional credentials; absence never prevents paper collection or delivery."""
    from botocore.exceptions import ClientError
    parameter = os.environ.get('JEV_CONFIG_PARAMETER')
    if not parameter or os.environ.get('JEV_MODE') != 'shadow':
        return
    try:
        raw = client('ssm').get_parameter(Name=parameter, WithDecryption=True)
        config = json.loads(raw['Parameter']['Value'])
        from .jev import MODEL
        if (not isinstance(config, dict) or config.get('model') != MODEL
                or not isinstance(config.get('api_key'), str) or not config['api_key'].strip()
                or not isinstance(config.get('focus'), str) or not 1 <= len(config['focus'].strip()) <= 2000):
            raise ValueError('Invalid Jev configuration')
        os.environ.update(TYPESAFE_API_KEY=config['api_key'].strip(), JEV_MODEL=config['model'], JEV_FOCUS=config['focus'].strip())
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'ParameterNotFound':
            raise


def configure_scholar():
    from botocore.exceptions import ClientError
    from . import scholar_email
    scholar_email.configure(None)
    parameter = os.environ.get('SCHOLAR_CONFIG_PARAMETER')
    if not parameter:
        return
    try:
        raw = client('ssm').get_parameter(Name=parameter, WithDecryption=True)
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ParameterNotFound':
            return
        raise
    config = json.loads(raw['Parameter']['Value'])
    if isinstance(config, dict) and config.get('provider') == 'graph':
        from .scholar_graph import validate_config
        validate_config(config)
        scholar_email.configure(config)
        return
    if (not isinstance(config, dict) or not config.get('verified_at')
            or not all(isinstance(config.get(k), str) and config[k] for k in ('host', 'user', 'password', 'folder'))
            or type(config.get('uidvalidity')) is not int or type(config.get('start_uid')) is not int):
        raise ValueError('Invalid verified Scholar mailbox configuration')
    scholar_email.configure(config)
