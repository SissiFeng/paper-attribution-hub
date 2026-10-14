"""Independent watchdog and private, durable incident notifications."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time

from . import registry, slack_app


def epoch(value):
    if isinstance(value, (int, float)):
        return value
    return dt.datetime.fromisoformat(value).timestamp() if value else 0


def collection_paused(settings):
    return settings.get('monitoring', {}).get('state') in ('awaiting_mailbox', 'paused')


def problems(health, settings, alarms, *, now=None):
    now = time.time() if now is None else now
    found = {}
    paused = collection_paused(settings)
    scholar = settings.get('monitoring', {}).get('source') == 'scholar'
    max_age = 45 * 60 if scholar else 4 * 3600 + 45 * 60
    age_label = '45 minutes' if scholar else '4 hours 45 minutes'
    last = epoch(
        health.get("last_success_at")
        or settings.get("last_collection")
        or health.get("installed_at")
    )
    if not paused and (not last or now - last > max_age):
        found["stale"] = (
            f"No complete successful collection in the last {age_label}."
        )
    if not paused and epoch(health.get("failed_task_at")) > last:
        found["task_failed"] = (
            "AWS reported a failed collection task; a later successful run is still pending."
        )
    summary = health.get("summary", {})
    non_collection_errors = set(summary.get('errors', [])) - {'openalex', 'arxiv', 'scholar_alert'}
    if health.get("last_exit", 0) != 0 and (not paused or non_collection_errors):
        found["run_failed"] = (
            "The most recent collection or delivery failed. Check /papers status and AWS logs."
        )
    if summary.get("delivery_counts", summary.get("counts", {})).get("sending"):
        found["delivery_uncertain"] = (
            "A paper delivery is uncertain. Check the existing Slack message before retrying."
        )
    oldest = epoch(summary.get("oldest_pending"))
    if (summary.get('active_subscribers', 0) or settings.get("enabled")) and oldest and now - oldest > 4 * 3600 + 45 * 60:
        found["delivery_backlog"] = (
            "A queued paper has waited over 4 hours 45 minutes for delivery."
        )
    if summary.get("unsynced", 0):
        found["ingestion_pending"] = (
            "Paper records are waiting for their paper-system storage receipt."
        )
    for alarm in alarms:
        collector_prefix = os.environ.get('MONITOR_COLLECTOR_ALARM_PREFIX')
        if paused and collector_prefix and alarm['AlarmName'].startswith(collector_prefix):
            continue
        if alarm["StateValue"] == "ALARM":
            found["alarm:" + alarm["AlarmName"]] = (
                "AWS reports a collector or Slack delivery failure."
            )
    return found


def notify(issues, *, key="monitor-incident", test=False, now=None):
    now = int(time.time()) if now is None else now
    settings = registry.get("settings")
    channel = settings.get("channel_id", "")
    if (
        not settings.get("owner_id")
        or not channel.startswith("D")
        or settings.get("tested_channel") != channel
    ):
        raise ValueError("Watchdog requires the tested private operator conversation")
    fingerprint = hashlib.sha256(json.dumps(sorted(issues)).encode()).hexdigest()
    previous = registry.get(key)
    if not previous and not issues:
        return {"status": "healthy", "sent": False}
    if previous.get("status") == "sending":
        # Acceptance is unknown; never turn a lost receipt into a repeated message.
        return {"status": "delivery_uncertain", "sent": False}
    if previous.get("fingerprint") == fingerprint:
        if previous.get("status") == "posted" or now < previous.get("retry_after", 0):
            return {"status": "unchanged", "sent": False}

    class AlreadyClaimed(Exception):
        pass

    def claim(current):
        if current != previous:
            raise AlreadyClaimed()
        current.clear()
        current.update(
            status="sending",
            fingerprint=fingerprint,
            issues=issues,
            at=now,
            channel=channel,
        )

    try:
        registry.change(key, claim)
    except AlreadyClaimed:
        return {"status": "claimed_elsewhere", "sent": False}
    title = (
        "AC Papers · "
        + ("TEST · " if test else "")
        + ("Monitoring needs attention" if issues else "Monitoring recovered")
    )
    body = (
        "\n".join("• " + v for v in issues.values())
        if issues
        else "Collection and delivery checks are healthy again."
    )
    if test:
        body += "\nThis is a labelled delivery test; it does not indicate a real system failure."
    try:
        config = registry.credentials()
        if not config:
            raise ValueError("Missing Slack credentials")
        result = slack_app.api(
            config["bot_token"],
            "chat.postMessage",
            {
                "channel": channel,
                "text": title + "\n" + body,
                "blocks": [slack_app.section("*" + title + "*\n" + body)],
            },
        )
        if not result.get("ts"):
            raise ValueError("Missing Slack receipt")
    except slack_app.SlackRejected:
        registry.put(
            key,
            {
                "status": "retryable",
                "fingerprint": fingerprint,
                "issues": issues,
                "retry_after": now + 900,
            },
        )
        raise
    # Other errors leave the durable 'sending' marker for reconciliation.
    registry.put(
        key,
        {
            "status": "posted",
            "fingerprint": fingerprint,
            "issues": issues,
            "at": now,
            "channel": channel,
            "ts": result["ts"],
        },
    )
    return {
        "status": "notified" if issues else "recovered",
        "sent": True,
        "channel": channel,
        "ts": result["ts"],
    }


def handler(event, context):
    if event.get("action") == "test":
        test_id = event.get("test_id", "")
        if not test_id or len(test_id) > 80 or not test_id.replace("-", "").isalnum():
            raise ValueError("A bounded test ID is required")
        issues = (
            {}
            if event.get("recovery")
            else {
                "test_failure": "Private failure-alert delivery path is being tested."
            }
        )
        return notify(issues, key="monitor-test:" + test_id, test=True)
    if event.get("source") == "aws.ecs":
        failed_at = epoch(event.get("time")) or time.time()
        registry.change(
            "monitor-health",
            lambda h: h.update(
                failed_task_at=max(failed_at, epoch(h.get("failed_task_at")))
            ),
        )
    settings, health = registry.get("settings"), registry.get("monitor-health")
    names = json.loads(os.environ.get("MONITOR_ALARMS", "[]"))
    alarms = (
        registry.client("cloudwatch").describe_alarms(AlarmNames=names)["MetricAlarms"]
        if names
        else []
    )
    issues = problems(health, settings, alarms)
    # An intentional pause is not recovery; preserve the previous incident.
    result = ({'status': settings['monitoring']['state'], 'sent': False}
              if collection_paused(settings) and not issues else notify(issues))
    registry.put(
        "monitor-watchdog",
        {"checked_at": int(time.time()), "issues": list(issues), **result},
    )
    if result['status'] == 'delivery_uncertain':
        raise RuntimeError('Watchdog delivery requires operator reconciliation')
    return result
