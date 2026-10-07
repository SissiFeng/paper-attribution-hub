"""Verify a real Scholar author-alert email before enabling the optional mailbox."""

from __future__ import annotations

import argparse
import datetime as dt
import email
import getpass
import json
from pathlib import Path
import sys

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_monitor import scholar_email
from paper_monitor.authors import Author


def active_authors(session, table):
    from boto3.dynamodb.conditions import Attr

    rows, kwargs = [], {"FilterExpression": Attr("pk").begins_with("author:")}
    while True:
        page = session.resource("dynamodb").Table(table).scan(**kwargs)
        rows.extend(json.loads(i["payload"]) for i in page["Items"])
        if not page.get("LastEvaluatedKey"):
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return [
        Author(r["name"], openalex_ids=r["openalex_ids"])
        for r in rows
        if r.get("status") == "active"
    ]


def verify(config, authors):
    with scholar_email.open_mailbox(config) as box:
        validity, start = (
            scholar_email.number(box, "UIDVALIDITY"),
            scholar_email.number(box, "UIDNEXT") - 1,
        )
        status, data = box.uid("search", None, "FROM", '"' + scholar_email.SENDER + '"')
        if status != "OK":
            raise ValueError("Cannot search the configured folder")
        matched = []
        for uid in sorted((int(i) for i in data[0].split()), reverse=True)[:30]:
            papers = scholar_email.parse_message(
                scholar_email.read_message(box, uid),
                authors,
                config.get("author_aliases"),
            )
            if papers:
                matched = papers
                break
        if not matched:
            raise ValueError(
                "No parseable author-alert email found in the last 30 Scholar messages"
            )
    verified = {
        **config,
        "uidvalidity": validity,
        "start_uid": start,
        "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    return verified, {
        "parsed_papers": len(matched),
        "tracked_authors": sorted({n for p in matched for n in p.tracked_authors}),
        "initial_mail_history": "Skipped; only messages arriving after activation will be imported",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="pas-sdl0-dev")
    parser.add_argument("--region", default="ca-central-1")
    parser.add_argument("--stack", default="paper-attribution-dev-author-monitor")
    parser.add_argument("--table", default="paper-attribution-dev-slack")
    parser.add_argument(
        "--author-map",
        type=Path,
        help="Optional JSON: Scholar display name -> verified watchlist name",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--status", action="store_true")
    modes.add_argument(
        "--check",
        action="store_true",
        help="Check existing mailbox read-only; do not reset its cursor",
    )
    modes.add_argument(
        "--validate-eml",
        type=Path,
        help="Parse an exported real email without enabling IMAP",
    )
    args = parser.parse_args(argv)
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    parameter = "/" + args.stack + "/scholar-mailbox"
    try:
        session.client("sts").get_caller_identity()
        if args.status or args.check:
            try:
                config = json.loads(
                    session.client("ssm").get_parameter(
                        Name=parameter, WithDecryption=True
                    )["Parameter"]["Value"]
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ParameterNotFound":
                    raise
                print(json.dumps({"status": "needs_mailbox", "enabled": False}))
                return 0 if args.status else 1
            if args.status:
                print(
                    json.dumps(
                        {
                            "status": "configured",
                            "verified_at": config.get("verified_at"),
                            "credential_shown": False,
                        }
                    )
                )
                return 0
        authors = active_authors(session, args.table)
        aliases = json.loads(args.author_map.read_text()) if args.author_map else {}
        if not isinstance(aliases, dict) or any(
            not isinstance(k, str) or v not in {a.name for a in authors}
            for k, v in aliases.items()
        ):
            raise ValueError(
                "Author aliases must map to active, verified watchlist names"
            )
        if args.validate_eml:
            papers = scholar_email.parse_message(
                email.message_from_bytes(args.validate_eml.read_bytes()),
                authors,
                aliases,
            )
            if not papers:
                raise ValueError("Not a supported author-publication alert")
            print(
                json.dumps(
                    {
                        "status": "real_email_parsed",
                        "papers": len(papers),
                        "mailbox_enabled": False,
                    }
                )
            )
            return 0
        if not args.check:
            if not sys.stdin.isatty():
                parser.error("Run in a terminal for hidden mailbox credential entry")
            config = {
                "host": input("IMAP TLS host (port 993): ").strip(),
                "user": input("Dedicated alert mailbox address: ").strip(),
                "folder": input("Alert folder [INBOX]: ").strip() or "INBOX",
                "password": getpass.getpass("Mailbox app password (hidden): ").strip(),
                "author_aliases": aliases,
            }
            if not all(config[k] for k in ("host", "user", "password")):
                raise ValueError("Mailbox settings are incomplete")
        verified, report = verify(config, authors)
        if not args.check:
            # Updating credentials must not silently discard unread messages from this mailbox.
            try:
                old = json.loads(
                    session.client("ssm").get_parameter(
                        Name=parameter, WithDecryption=True
                    )["Parameter"]["Value"]
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ParameterNotFound":
                    raise
                old = {}
            if old:
                if any(
                    old.get(k) != verified[k]
                    for k in ("host", "user", "folder", "uidvalidity")
                ):
                    raise ValueError(
                        "Mailbox identity changed; reconcile its existing cursor before replacing it"
                    )
                verified["start_uid"] = old["start_uid"]
            session.client("ssm").put_parameter(
                Name=parameter,
                Value=json.dumps(verified),
                Type="SecureString",
                Overwrite=True,
                Description="Verified read-only Scholar alert mailbox; no website scraping",
            )
        print(
            json.dumps(
                {"status": "checked" if args.check else "verified_and_saved", **report},
                ensure_ascii=False,
            )
        )
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(
            "Scholar configuration failed: "
            + type(exc).__name__
            + ". No unverified credentials were saved.",
            file=sys.stderr,
        )
        print(
            "Check the host/app-password, dedicated folder, real author-alert format and watchlist mapping.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
