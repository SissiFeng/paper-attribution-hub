import copy
import importlib
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

from paper_monitor import http, openalex
from test_monitor import OA


def rejected():
    return urllib.error.HTTPError(
        'https://api.openalex.org/works?api_key=secret-key', 401,
        'secret-response', {}, io.BytesIO(b'secret-body'),
    )


def test_second_page_auth_failure_does_not_accept_partial_baseline(env):
    _, run, statuses, _, monkeypatch, path = env
    calls = []

    def fetch(url, params):
        calls.append(copy.deepcopy(params))
        if params.get('cursor') == 'second-page':
            raise rejected()
        return dict(OA, meta={'next_cursor': 'second-page'})

    monkeypatch.setattr(http, 'get_json', fetch)
    assert run() == 1
    assert len(calls) == 2
    assert statuses() == {}
    from paper_monitor.store import Store
    store = Store(path / 'state.db')
    assert not store.meta('initialized')
    store.close()


def test_auth_diagnostic_explains_fix_without_secret_values(monkeypatch):
    monkeypatch.setattr(http, 'get_json', lambda *_: (_ for _ in ()).throw(rejected()))
    with pytest.raises(openalex.AuthenticationError) as exc:
        list(openalex.recent_works({'A1': 'A'}, '2026-10-01'))
    message = str(exc.value)
    assert 'HTTP 401' in message and 'OPENALEX_PARAMETER' in message
    assert 'secret' not in message


def test_key_validation_reaches_distinct_second_cursor_page(monkeypatch):
    calls = []

    def fetch(url, params):
        calls.append(copy.deepcopy(params))
        return {'results': [{'id': 'W' + str(len(calls))}],
                'meta': {'next_cursor': 'second-page'}}

    monkeypatch.setattr(http, 'get_json', fetch)
    openalex.validate_api_key(' secret-key ')
    assert [c['cursor'] for c in calls] == ['*', 'second-page']
    assert all(c['api_key'] == 'secret-key' and c['per-page'] == 1 for c in calls)


@pytest.mark.parametrize('second', [
    {'results': []}, {'results': [{'id': 'W1'}]}, {'results': [{}]},
])
def test_key_validation_rejects_missing_or_repeated_second_page(monkeypatch, second):
    pages = iter([{'results': [{'id': 'W1'}], 'meta': {'next_cursor': 'second-page'}}, second])
    monkeypatch.setattr(http, 'get_json', lambda *_: next(pages))
    with pytest.raises(ValueError):
        openalex.validate_api_key('secret-key')


def configure_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / 'deploy'))
    configure = importlib.import_module('configure_openalex')
    monkeypatch.setattr(sys, 'argv', ['configure_openalex.py'])
    monkeypatch.setattr(configure.getpass, 'getpass', lambda _: 'secret-key')
    return configure


def test_rejected_second_page_key_is_never_saved(monkeypatch):
    configure = configure_module(monkeypatch)
    calls = []

    def fetch(url, params):
        calls.append(copy.deepcopy(params))
        if len(calls) == 2:
            raise rejected()
        return {'results': [{'id': 'W1'}], 'meta': {'next_cursor': 'second-page'}}

    monkeypatch.setattr(http, 'get_json', fetch)
    monkeypatch.setattr(configure.subprocess, 'run', lambda *_a, **_k: pytest.fail('must not save'))
    with pytest.raises(openalex.AuthenticationError):
        configure.main()
    assert len(calls) == 2


def test_verified_key_is_saved_encrypted_via_stdin_only(monkeypatch):
    configure = configure_module(monkeypatch)
    order = []
    monkeypatch.setattr(openalex, 'validate_api_key', lambda key: order.append(('validated', key)))

    def save(args, **kwargs):
        assert order == [('validated', 'secret-key')]
        assert 'secret-key' not in ' '.join(args)
        payload = json.loads(kwargs['input'])
        assert payload['Value'] == 'secret-key'
        assert payload['Type'] == 'SecureString'
        assert payload['Name'] == '/paper-attribution-dev-author-monitor/openalex-api-key'
        assert kwargs['capture_output'] and kwargs['check']
        order.append(('saved', None))

    monkeypatch.setattr(configure.subprocess, 'run', save)
    configure.main()
    assert order[-1][0] == 'saved'
