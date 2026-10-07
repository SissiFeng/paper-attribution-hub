"""Provider transport contracts use fake SDKs, never paid credentials or the network."""
import sys
from types import SimpleNamespace
import pytest
from app.config import settings
from app.services.grounded_answer_service import generate_grounded_answer, generation_status


@pytest.mark.parametrize('provider', ['anthropic', 'kimi'])
def test_provider_receives_bounded_evidence_prompt_and_no_secret_output(monkeypatch, provider):
    calls = {}
    key = 'test-key-not-a-live-credential'
    monkeypatch.setattr(settings, 'llm_provider', provider)
    monkeypatch.setattr(settings, 'anthropic_api_key', key if provider == 'anthropic' else '')
    monkeypatch.setattr(settings, 'kimi_api_key', key if provider == 'kimi' else '')
    def create(**kwargs):
        calls['request'] = kwargs
        if provider == 'anthropic':
            return SimpleNamespace(content=[SimpleNamespace(text='Evidence-supported answer [1].')])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Evidence-supported answer [1].'))])
    def client(**kwargs):
        calls['client'] = kwargs
        return SimpleNamespace(messages=SimpleNamespace(create=create), chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setitem(sys.modules, 'anthropic' if provider == 'anthropic' else 'openai',
        SimpleNamespace(**{'Anthropic' if provider == 'anthropic' else 'OpenAI': client}))
    answer, model = generate_grounded_answer('What was measured?', '[1] The measured value is 250 mV.',
        conversation=[{'role':'user','content':'previous question'}], page_context='untrusted page')
    assert answer == 'Evidence-supported answer [1].'
    assert model != 'retrieval-only'
    assert calls['client']['api_key'] == key
    assert calls['client']['timeout'] == 8.0 and calls['client']['max_retries'] == 0
    prompt = str(calls['request'])
    assert '250 mV' in prompt and 'untrusted' in prompt and 'citing them as [N]' in prompt
    assert key not in prompt and key not in str(generation_status())


@pytest.mark.parametrize('provider', ['anthropic', 'kimi'])
def test_provider_failure_returns_explicit_error_without_exception_text(monkeypatch, provider):
    monkeypatch.setattr(settings, 'llm_provider', provider)
    monkeypatch.setattr(settings, provider+'_api_key', 'not-a-real-key')
    def client(**kwargs):
        raise RuntimeError('Sensitive provider details should not escape')
    monkeypatch.setitem(sys.modules, 'anthropic' if provider == 'anthropic' else 'openai',
        SimpleNamespace(**{'Anthropic' if provider == 'anthropic' else 'OpenAI': client}))
    assert generate_grounded_answer('question', '[1] source') == (None, 'provider-error')
