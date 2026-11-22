# From event deliveries to timelines

Supply structured event records with unique source IDs, timezone-aware timestamps, service names, severity and messages. Use a trace ID when available. Untraced events require an explicit fingerprint and are grouped only with events from the same service. This avoids joining unrelated services solely because their timestamps happen to be close.

Matching deliveries with the same event ID are counted once, with their delivery count retained. Conflicting payloads that reuse an ID stop the run. Time is normalized to UTC. A gap greater than gap_seconds starts a new episode even if a trace identifier is reused. Within an episode you can inspect participating services, event IDs, peak severity and time range.

Approve the episodes relevant to the investigation. The JSON Lines export interleaves their events in chronological order, keeping trace identifiers and original messages. A separate CSV indexes the episodes. Submit sanitized messages appropriate to the target audience. This pipeline groups evidence; it cannot establish a root cause or reconstruct missing log events.
