"""Native Slack views and a non-retrying Web API client."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .slack import _esc, format_message

SCOPES = ['chat:write', 'commands', 'im:write']


class SlackRejected(ValueError):
    """Slack explicitly rejected a request (safe to retry after fixing cause)."""


def retry_delay(exc):
    """Only explicit rejection is safe to retry; 5xx/timeouts may be accepted."""
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
        try:
            return max(1, int((exc.headers or {}).get('Retry-After', '60')))
        except (TypeError, ValueError):
            return 60
    if isinstance(exc, SlackRejected) or isinstance(exc, urllib.error.HTTPError) and exc.code < 500:
        return 900
    return None


def api(token, method, payload, timeout=8):
    request = urllib.request.Request('https://slack.com/api/' + method,
        data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer ' + token,
                                                    'Content-Type': 'application/json; charset=utf-8'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if not result.get('ok'):
        # Do not print payloads, tokens, response_url, or request bodies.
        raise SlackRejected('Slack: ' + str(result.get('error', 'unknown_error')))
    return result


def paper_key(p):
    return hashlib.sha256((p.doi or p.openalex_id or p.arxiv_id or str(p.title_key)).encode()).hexdigest()[:32]


def button(label, action, value='1', **extra):
    return {'type': 'button', 'text': {'type': 'plain_text', 'text': label},
            'action_id': action, 'value': value, **extra}


def section(text):
    return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text[:3000]}}


def paper_link(p):
    return format_message(p)['blocks'][0]['text']['text'].split('\n')[0]


def card(p, pas_id=None):
    message = format_message(p)
    key = paper_key(p)
    buttons = []
    base = os.environ.get('PAS_PUBLIC_URL', '').rstrip('/')
    if base.startswith('https://'):
        if pas_id:
            path = '/papers/' + urllib.parse.quote(pas_id, safe='')
        elif p.doi:
            path = '/papers?' + urllib.parse.urlencode({'doi': p.doi})
        else:
            identity = p.openalex_id or p.arxiv_id
            path = '/papers/monitor_' + hashlib.sha256(identity.encode()).hexdigest()[:32] if identity else ''
        if path:
            buttons.append(button('Open in PAS ↗', 'open_pas', key, url=base + path, style='primary'))
    if p.url and p.url.startswith(('https://', 'http://')):
        buttons.append(button('Read paper ↗', 'read_paper', key, url=p.url[:3000]))
    buttons.extend([button('👍 Relevant', 'feedback_yes', key), button('👎 Not relevant', 'feedback_no', key)])
    buttons.append({'type': 'overflow', 'action_id': 'paper_more', 'options': [
        {'text': {'type': 'plain_text', 'text': 'Report incorrect author match'}, 'value': key}]})
    message['blocks'].insert(0, {'type': 'context', 'elements': [{'type': 'plain_text', 'text': 'AC  /  NEW PUBLICATION'}]})
    message['blocks'].append({'type': 'actions', 'elements': buttons})
    message.update(unfurl_links=False, unfurl_media=False)
    return message


def digest(papers, *, preview=False):
    title = 'Connection test · paper preview' if preview else 'AC · Weekly publications'
    lead = f'*{len(papers)} papers*' + (' from the monitoring catalogue. This is a test preview.' if preview else ' newly detected and saved in the paper system.')
    names = sorted({name for p in papers for name in p.tracked_authors})
    blocks = [{'type': 'header', 'text': {'type': 'plain_text', 'text': title}}, section(lead)]
    if names:
        blocks.append(section('*Tracked authors*\n' + _esc(', '.join(names))[:2200]))
    blocks.extend([{'type': 'divider'}, section('Paper details and feedback buttons are in the thread.\nFeedback is recorded for review; it does not automatically hide papers.')])
    return {'text': f'{title}: {len(papers)} papers', 'blocks': blocks, 'unfurl_links': False, 'unfurl_media': False}


def jev_status(settings):
    state = settings.get('jev_shadow', {}).get('status')
    return {'needs_configuration': 'Jev suggestions: waiting for an API key.',
            'ready': 'Jev suggestions: available for private review.',
            'degraded': 'Jev suggestions: evaluation interrupted; existing results remain available.',
            'daily_limit_reached': 'Jev suggestions: today’s evaluation limit reached; available results can be reviewed.',
            'off': 'Jev suggestions: switched off.'}.get(state, 'Jev suggestions: awaiting the first evaluation run.')


def shadow_card(paper, decision):
    message = card(paper)
    message['blocks'][0]['elements'][0]['text'] = 'AC  /  JEV READING SUGGESTION · EXPERIMENTAL'
    step = {'fulltext_needed': 'Consult the full paper', 'metadata_sufficient': 'Metadata sufficient for initial triage',
            'manual_review': 'Human review needed'}[decision['next_step']]
    message['blocks'].insert(-1, section(f"*Reading priority:* {decision['priority_score']:.2f}/4 · *Next step:* {step}\n"
        'Based on title and abstract only. No full paper was read or downloaded.'))
    message['text'] = 'Experimental reading suggestion: ' + message['text']
    return message


TASK_LABELS = {'author_identity': 'Author identity', 'version_relation': 'Publication versions',
    'reading_priority': 'Reading priority', 'analysis_route': 'Full text / model routing',
    'retrieval_route': 'Question retrieval path', 'answer_evidence': 'Answer evidence',
    'review_priority': 'Human review priority', 'graph_relation': 'Knowledge graph relations'}


def decisions_message(entries):
    blocks = [{'type': 'header', 'text': {'type': 'plain_text', 'text': 'AC · Eight Jev workflows'}},
              section('All workflows provide experimental suggestions. Existing decisions stay in effect. '
                      'No evaluated result means no prediction, not a negative finding.')]
    for task, label in TASK_LABELS.items():
        item = next((e for e in entries if e.get('task') == task), None)
        decision = (item or {}).get('decision', {})
        summary = str(decision.get('choice', decision.get('score', item.get('status') if item else 'Not evaluated yet')))
        block = section('*' + label + '*\n' + _esc(summary))
        if item and item.get('status') == 'ok':
            block['accessory'] = button('Review suggestion', 'jev_feedback', item['decision_id'])
        blocks.append(block)
    return {'text': 'Eight Jev workflows · experimental suggestions', 'blocks': blocks}


def decision_feedback_modal(entry):
    from .jev_tasks import question
    spec = question(entry['task'])
    criteria = spec['criteria']
    choices = list(enumerate(criteria)) if isinstance(criteria, list) else list(criteria.items())
    options = [{'text': {'type': 'plain_text', 'text': (str(k)+' · '+v)[:75]}, 'value': str(k)} for k, v in choices]
    state = entry.get('state', {})
    public = json.dumps(state, ensure_ascii=False, indent=2)
    return {'type': 'modal', 'callback_id': 'jev_feedback', 'private_metadata': entry['decision_id'],
        'title': {'type': 'plain_text', 'text': 'Review Jev suggestion'},
        'submit': {'type': 'plain_text', 'text': 'Save review'}, 'close': {'type': 'plain_text', 'text': 'Cancel'},
        'blocks': [section('Choose your judgement. This records evaluation feedback; it does not merge authors, change classification or modify the graph.'),
                   section(_esc(public)[:2800]), {'type': 'input', 'block_id': 'label',
                   'label': {'type': 'plain_text', 'text': TASK_LABELS[entry['task']]},
                   'element': {'type': 'static_select', 'action_id': 'value', 'options': options}}]}


def manifest(base):
    return {'display_information': {'name': 'AC Papers', 'description': 'New publications from the AC author watchlist', 'background_color': '#263C36'},
        'features': {'bot_user': {'display_name': 'AC Papers', 'always_online': False},
            'app_home': {'home_tab_enabled': True, 'messages_tab_enabled': True, 'messages_tab_read_only_enabled': False},
            'slash_commands': [{'command': '/papers', 'url': base + '/slack',
                'description': 'Connect, preview publications, and manage the author watchlist',
                'usage_hint': 'connect · test · review · decisions · start · status · authors · add · pause', 'should_escape': False}]},
        'oauth_config': {'scopes': {'bot': SCOPES}},
        'settings': {'event_subscriptions': {'request_url': base + '/slack', 'bot_events': ['app_home_opened']},
                     'interactivity': {'is_enabled': True, 'request_url': base + '/slack'},
                     'socket_mode_enabled': False, 'token_rotation_enabled': False}}


def monitor_status(settings):
    monitoring = settings.get('monitoring', {})
    summary = settings.get('monitor_summary', {})
    if monitoring.get('source') == 'scholar':
        state = monitoring.get('state', 'awaiting_mailbox')
        if state != 'active':
            return ('Google Scholar author alerts: waiting for shared-mailbox application authorization.\n'
                    'Automatic collection is paused. OpenAlex polling is disabled.\n'
                    'Planned checks: every 15 minutes; subscriptions and stored papers are preserved.')
        stages = '\n'.join(label + ': ' + str(summary.get(key) or 'not verified yet') for label, key in (
            ('Last successful mailbox check', 'last_mailbox_poll_ok_at'),
            ('Last successful PAS sync', 'last_pas_sync_ok_at'),
            ('Last successful delivery check', 'last_delivery_ok_at')))
        review = summary.get('mail_quarantined', 0) + summary.get('mail_fetch_pending', 0)
        return ('Source: Google Scholar author-alert emails, read from the designated Microsoft 365 folder.\n'
                'Mailbox checks: every 15 minutes; delivery follows storage in PAS.\n'
                'Timing depends on when Google sends the alert. OpenAlex polling is disabled.\n'
                f'{stages}\nEmails needing review/retry: {review}.\n'
                'An empty successful mailbox check means no new alert, not a connection failure.')
    summary = settings.get('monitor_summary', {})
    mailbox = 'connected' if summary.get('mailbox') == 'enabled' else 'waiting for mailbox setup'
    return ('Sources: OpenAlex; Google Scholar email: '+mailbox+'.\n'
            'Recent papers: checked every 4 hours. Wider scan: past year, weekly.\n'
            'Operational alerts: private messages on failures, overdue runs or delivery backlog.')


def home(settings, rows, page=0):
    active = sum(r.get('status') == 'active' for r in rows)
    pending = sum(r.get('status') == 'needs_review' for r in rows)
    status = 'Updates enabled' if settings.get('enabled') else 'Updates paused'
    destination = 'Private messages to you' if settings.get('channel_id', '').startswith('D') else 'Not connected'
    admin = settings.get('can_manage_authors', False)
    scholar = settings.get('monitoring', {}).get('source') == 'scholar'
    controls = ([button('Add an author', 'add_author')] if admin and not scholar else []) + [button('Send me a test', 'test'),
        button('Pause my updates' if settings.get('enabled') else 'Start my updates',
               'notifications_pause' if settings.get('enabled') else 'notifications_start'), button('Refresh', 'home', str(page))]
    blocks = [{'type': 'header', 'text': {'type': 'plain_text', 'text': 'AC · Publication watchlist'}},
        section(f'*{status}* · {destination}\n{len(rows)} authors in the list · {active} active · {pending} need identity review\nNew papers are sent after storage. Weekly recaps run with the collector. Watchlist membership does not confirm a Scholar alert subscription.'),
        {'type': 'actions', 'elements': controls},
        section(monitor_status(settings)),
        section(jev_status(settings) + '\nExperimental suggestions only; regular paper collection and delivery continue as usual.'),
        {'type': 'actions', 'elements': [button('Review Jev suggestions', 'jev_review'), button('Eight Jev workflows', 'jev_decisions')]},
        section('Your subscription and pause controls affect only your private messages. New subscribers receive future discoveries; historical papers are available in previews. The shared author list is managed by its administrator.'), {'type': 'divider'}]
    base = os.environ.get('PAS_PUBLIC_URL', '').rstrip('/')
    if base.startswith('https://'):
        blocks.insert(3, {'type': 'actions', 'elements': [button('Open PAS ↗', 'open_pas', url=base + '/')]})
    page = max(0, min(page, max(0, (len(rows) - 1) // 20)))
    for row in rows[page * 20:(page + 1) * 20]:
        label = {'active': 'Watchlist active' if scholar else 'Monitoring', 'paused': 'Paused', 'needs_review': 'Identity review needed'}[row['status']]
        text = f"*{_esc(row['name'])}* · {label}\n{_esc(row.get('institution', ''))}"
        if row.get('openalex_ids'):
            text += f" · <https://openalex.org/{row['openalex_ids'][0]}|Author profile>"
        if scholar:
            coverage = row.get('scholar', {})
            label = ('Publication email received' if coverage.get('publication_messages') else
                     'Subscription confirmed' if coverage.get('subscription_confirmed') else
                     'Alert created; confirmation pending' if coverage.get('alert_created') else
                     'Alert setup not verified')
            text += '\nScholar: ' + label
            profile = coverage.get('profile_url', '')
            if profile.startswith('https://scholar.google.com/citations?'):
                text += f' · <{_esc(profile)}|Scholar profile>'
            if coverage.get('last_received_at'):
                text += '\nLast publication email: ' + _esc(coverage['last_received_at'])
        if row.get('note') and row['status'] == 'needs_review':
            text += '\n' + _esc(row['note'])[:500]
        block = section(text)
        if admin and not scholar and row['status'] != 'needs_review':
            action = 'author_pause' if row['status'] == 'active' else 'author_resume'
            block['accessory'] = button('Pause' if action == 'author_pause' else 'Resume', action, row['person_id'])
        blocks.append(block)
    blocks.append({'type': 'actions', 'elements': [button('Previous', 'home_previous', str(max(0, page-1))), button('Next', 'home_next', str(page+1))]})
    return {'type': 'home', 'blocks': blocks}


def add_modal():
    return {'type': 'modal', 'callback_id': 'author_search', 'title': {'type': 'plain_text', 'text': 'Add an author'},
        'submit': {'type': 'plain_text', 'text': 'Find candidates'}, 'close': {'type': 'plain_text', 'text': 'Cancel'},
        'blocks': [section('Enter an ORCID or a name. Review the matching profiles before monitoring starts. The next collection every 4 hours includes papers from the last 90 days.'),
            {'type': 'input', 'block_id': 'query', 'label': {'type': 'plain_text', 'text': 'Name or ORCID'},
             'element': {'type': 'plain_text_input', 'action_id': 'value', 'max_length': 150}}]}


def searching_view():
    return {'type': 'modal', 'title': {'type': 'plain_text', 'text': 'Finding authors'},
            'close': {'type': 'plain_text', 'text': 'Close'},
            'blocks': [section('Looking up author profiles… This normally takes a few seconds. No author has been added yet.')]}


def candidates_view(key, candidates):
    view = {'type': 'modal', 'callback_id': 'author_choose', 'private_metadata': key,
            'title': {'type': 'plain_text', 'text': 'Confirm the author'}, 'close': {'type': 'plain_text', 'text': 'Cancel'}}
    if not candidates:
        view['blocks'] = [section('No matching profile was found. Try a full name or an ORCID with `/papers add`.')]
        return view
    options = []
    for a in candidates:
        hint = ''
        if a.get('jev_advice'):
            advice = a['jev_advice']
            hint = ' · Jev: ' + str(advice.get('decision', {}).get('choice', advice['status']))
        options.append({'text': {'type': 'plain_text', 'text': (a['name'] + ' · ' + a['institution'])[:75]},
                        'description': {'type': 'plain_text', 'text': (a['id'] + hint + ' · ' + str(a['works_count']) + ' works')[:75]}, 'value': a['id']})
    view['submit'] = {'type': 'plain_text', 'text': 'Monitor author'}
    view['blocks'] = [section('Choose only the profile that belongs to your author. The institution and publication count help distinguish namesakes.'),
        {'type': 'input', 'block_id': 'author', 'label': {'type': 'plain_text', 'text': 'Author profile'},
         'element': {'type': 'static_select', 'action_id': 'value', 'options': options}},
        section('\n'.join(f"<https://openalex.org/{a['id']}|{_esc(a['name'])} · view publications>" for a in candidates)[:2900])]
    return view
