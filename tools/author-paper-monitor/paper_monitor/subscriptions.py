"""Personal subscriptions inside the installed workspace; shared administration stays separate."""
import datetime as dt
import re

from . import registry, slack_app


def key(user):
    if not isinstance(user, str) or not re.fullmatch(r'[UW][A-Z0-9]+', user):
        raise ValueError('A Slack member identity is required')
    return 'subscriber:' + user


def request(user, enabled=None):
    settings = registry.get('settings')

    def edit(current):
        if not current:
            current.update(user_id=user, enabled=True,
                           since=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'))
            # Preserve the operator's existing pause setting and verified private connection.
            if user == settings.get('owner_id'):
                current.update(enabled=bool(settings.get('enabled')),
                               channel_id=settings.get('channel_id', ''), welcome_status='posted')
        if enabled is not None:
            current['enabled'] = enabled

    return registry.change(key(user), edit)


def all_members():
    from boto3.dynamodb.conditions import Attr
    rows, args = [], {'FilterExpression': Attr('pk').begins_with('subscriber:')}
    while True:
        import json
        page = registry.table().scan(**args)
        rows.extend(json.loads(item['payload']) for item in page['Items'])
        if not page.get('LastEvaluatedKey'):
            return sorted(rows, key=lambda row: row['user_id'])
        args['ExclusiveStartKey'] = page['LastEvaluatedKey']


def view(user):
    shared = registry.get('settings')
    personal = registry.get(key(user))
    return {**shared, 'enabled': personal.get('enabled', False),
            'channel_id': personal.get('channel_id', ''), 'subscribed': bool(personal),
            'can_manage_authors': user == shared.get('owner_id')}


def connect(user, token):
    personal = registry.get(key(user)) or request(user)
    if not personal.get('channel_id'):
        result = slack_app.api(token, 'conversations.open', {'users': user})
        channel = result['channel']['id']
        if not channel.startswith('D'):
            raise ValueError('Expected a private direct conversation')
        personal = registry.change(key(user), lambda row: row.update(channel_id=channel))
    if not personal['channel_id'].startswith('D'):
        raise ValueError('Personal updates require a private conversation')
    return personal


def welcome(user, token):
    personal = connect(user, token)
    claimed = False

    def claim(row):
        nonlocal claimed
        claimed = not row.get('welcome_status')
        if claimed:
            row['welcome_status'] = 'sending'

    registry.change(key(user), claim)
    if claimed:
        try:
            result = slack_app.api(token, 'chat.postMessage', {'channel': personal['channel_id'],
                'text': 'Welcome to AC Papers. Your private paper subscription is ready. ' +
                        ('Automatic updates are on.' if personal['enabled'] else 'Your updates are paused.') +
                        ' We check the shared AC author list every 4 hours and send a weekly recap. '
                        'Use `/papers test` for a real-paper preview, `/papers pause` to pause only your updates, '
                        'or `/papers start` to resume. Historical papers are not sent as new discoveries.'})
            if not result.get('ts'):
                raise ValueError('Missing welcome receipt')
        except slack_app.SlackRejected:
            registry.change(key(user), lambda row: row.pop('welcome_status', None))
            raise
        registry.change(key(user), lambda row: row.update(welcome_status='posted', welcome_ts=result['ts']))
    return personal
