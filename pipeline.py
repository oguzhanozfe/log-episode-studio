"""Group explicitly submitted structured log records into reviewable time windows."""

import csv
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

TITLE = "Log Episode Studio"
DESCRIPTION = "Reduce repeat deliveries and group trace-linked or fingerprint-linked log events into reviewable incident timelines."
PROMPT = "Explain observed sequence, gaps and services using event IDs. Correlation across time or trace IDs is evidence for investigation rather than proof of causation."
SEVERITY = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}


def identifier(value, field="id"):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,119}", value
    ):
        raise ValueError(
            f"Invalid {field}: use a short stable identifier without spaces."
        )
    return value


def text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError(f"{field} must be nonempty text up to 4,000 characters.")
    return value.strip()


def objects(value, field, cap=500):
    if (
        not isinstance(value, list)
        or len(value) > cap
        or any(not isinstance(row, dict) for row in value)
    ):
        raise ValueError(f"{field} must be an array of at most {cap} objects.")
    return value


def csv_file(columns, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue()


def selected(evidence, approved):
    available = {item["id"]: item for item in evidence["candidates"]}
    seen = set()
    result = []
    for item in approved:
        key = item["id"]
        if key not in available or key in seen:
            raise ValueError("Approval contains an unknown or duplicate decision.")
        seen.add(key)
        result.append(available[key])
    return result


def instant(raw):
    dt = datetime.fromisoformat(text(raw, "timestamp").replace("Z", "+00:00"))
    if dt.utcoffset() is None:
        raise ValueError("Every timestamp must include an offset.")
    return dt.astimezone(timezone.utc)


def prepare(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Provide events and a gap_seconds window.")
    gap = data.get("gap_seconds", 120)
    if type(gap) != int or not 1 <= gap <= 86400:
        raise ValueError("gap_seconds must be between 1 and 86,400.")
    by_id = {}
    deliveries = defaultdict(int)
    buckets = defaultdict(list)
    times = {}
    for item in objects(data.get("events"), "events", 3000):
        k = identifier(item.get("id"))
        when = instant(item.get("timestamp"))
        service = identifier(item.get("service"), "service")
        trace = (
            identifier(item["trace_id"], "trace_id")
            if item.get("trace_id") is not None
            else None
        )
        fingerprint = (
            identifier(item["fingerprint"], "fingerprint")
            if item.get("fingerprint") is not None
            else None
        )
        if not trace and not fingerprint:
            raise ValueError("Untraced events need an explicit fingerprint.")
        level = text(item.get("level"), "level").upper()
        if level not in SEVERITY:
            raise ValueError("Use DEBUG, INFO, WARN, ERROR or FATAL.")
        row = {
            "id": k,
            "timestamp": when.isoformat().replace("+00:00", "Z"),
            "service": service,
            "trace_id": trace,
            "fingerprint": fingerprint,
            "level": level,
            "message": text(item.get("message"), "message"),
        }
        if k in by_id and by_id[k] != row:
            raise ValueError(f"Conflicting payloads reuse event ID {k}.")
        deliveries[k] += 1
        if k not in by_id:
            by_id[k] = row
            times[k] = when
            bucket = (
                ("trace", trace) if trace else ("fingerprint", service, fingerprint)
            )
            buckets[bucket].append(k)
    candidates = []
    for bucket, ids in sorted(buckets.items()):
        blocks = []
        for k in sorted(ids, key=lambda v: (times[v], v)):
            if not blocks or (times[k] - times[blocks[-1][-1]]).total_seconds() > gap:
                blocks.append([])
            blocks[-1].append(k)
        for block in blocks:
            severity = max((by_id[k]["level"] for k in block), key=SEVERITY.get)
            candidates.append(
                {
                    "id": "episode:" + block[0],
                    "action": "Include episode in incident timeline",
                    "evidence_ids": block,
                    "correlation": list(bucket),
                    "start": by_id[block[0]]["timestamp"],
                    "end": by_id[block[-1]]["timestamp"],
                    "max_severity": severity,
                    "services": sorted({by_id[k]["service"] for k in block}),
                    "events": len(block),
                }
            )
    candidates.sort(key=lambda c: (times[c["evidence_ids"][0]], c["id"]))
    records = [
        dict(by_id[k], deliveries=deliveries[k])
        for k in sorted(by_id, key=lambda v: (times[v], v))
    ]
    return {
        "summary": f"{len(records)} unique events grouped into {len(candidates)} episodes.",
        "metrics": {
            "Deliveries": sum(deliveries.values()),
            "Unique events": len(records),
            "Episodes": len(candidates),
            "Repeat deliveries": sum(deliveries.values()) - len(records),
        },
        "records": records,
        "candidates": candidates,
    }


def export(data, evidence, approved):
    included = selected(evidence, approved)
    by_event = {k: c["id"] for c in included for k in c["evidence_ids"]}
    lines = (
        dict(r, episode_id=by_event[r["id"]])
        for r in evidence["records"]
        if r["id"] in by_event
    )
    rows = [
        [
            c["id"],
            c["start"],
            c["end"],
            c["max_severity"],
            c["events"],
            ";".join(c["services"]),
        ]
        for c in sorted(included, key=lambda x: instant(x["start"]))
    ]
    return {
        "incident-timeline.jsonl": "".join(
            json.dumps(x, ensure_ascii=False) + "\n" for x in lines
        ),
        "episode-index.csv": csv_file(
            [
                "episode",
                "start_utc",
                "end_utc",
                "peak_severity",
                "unique_events",
                "services",
            ],
            rows,
        ),
    }
