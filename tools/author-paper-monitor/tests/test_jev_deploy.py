import importlib
import json
from pathlib import Path
from types import SimpleNamespace


def test_jev_secret_is_optional_at_ecs_start_and_scoped_to_task_role(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'deploy'))
    deploy = importlib.import_module('aws')
    args = SimpleNamespace(stack='monitor', bucket='bucket', region='ca-central-1', cluster='cluster',
                           slack_app='slack', slack_parameter=None, jev_shadow=True, enable_schedule=True)
    task = {'containerDefinitions': [{}]}
    network = {'subnets': ['s1'], 'securityGroups': ['g1'], 'assignPublicIp': 'ENABLED'}
    doc = deploy.template(args, '123', task, network, 'image@sha256:abc', 'bundle.zip', 'abc', '/db')
    container = doc['Resources']['Task']['Properties']['ContainerDefinitions'][0]
    env = {v['Name']: v['Value'] for v in container['Environment']}
    assert env['JEV_CONFIG_PARAMETER'] == '/monitor/jev'
    assert env['JEV_MODE'] == 'shadow'
    assert 'jev' not in json.dumps(container['Secrets'])  # A missing optional key cannot fail task startup.
    statements = doc['Resources']['TaskRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
    assert any(s['Action'] == 'ssm:GetParameter' and s['Resource'] == 'arn:aws:ssm:ca-central-1:123:parameter/monitor/jev' for s in statements)
    args.jev_shadow = False
    off = deploy.template(args, '123', task, network, 'image', 'bundle.zip', 'abc', '/db')
    assert '/monitor/jev' not in json.dumps(off)


def test_slack_identity_advice_has_only_the_scoped_jev_parameter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'deploy'))
    deploy = importlib.import_module('slack_aws')
    args = SimpleNamespace(stack='slack', bucket='bucket', region='ca-central-1')
    doc = deploy.template(args, '123', 'bundle.zip')
    policies = json.dumps(doc['Resources']['Role']['Properties']['Policies'])
    assert 'production/outbox/jev-shadow.json' in policies
    assert 'parameter/paper-attribution-dev-author-monitor/jev' in policies
    assert 'parameter/*' not in policies


def test_backend_overlay_refuses_drift_and_keeps_unrelated_code(monkeypatch):
    import pytest
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]/'deploy'))
    deploy = importlib.import_module('jev_backend')
    with pytest.raises(ValueError, match='drifted'):
        deploy.replace_once('missing target', 'anchor', 'replacement')
    with pytest.raises(ValueError, match='drifted'):
        deploy.replace_once('anchor anchor', 'anchor', 'replacement')
    assert deploy.replace_once('unrelated\nanchor\nkeep', 'anchor', 'hook') == 'unrelated\nhook\nkeep'
