# Decisions

Judgement calls, with the alternatives considered. Numbered so code comments and reviews can point at them.

## D-001 Kafka key = engine_id, 6 partitions

Every reading for one engine lands on the same partition, so Kafka keeps them in order without any global
ordering. Six partitions let up to six scorer instances share the load (`docker compose up --scale scorer=3`).
*Alternative:* random keys spread load more evenly, but an engine's cycles could then be scored out of order.

## D-002 At-least-once delivery, made effectively-once in Postgres

Kafka offsets are committed manually, only after the database transaction for the batch has committed. Every
table is keyed on a natural key (`(engine_id, cycle)`, `(engine_id, band)`, `(topic, partition, offset)`), so a
redelivered batch is absorbed by `ON CONFLICT`. Tested in `tests/test_scorer_db.py`.
*Alternatives:* auto-commit (can lose messages if the process dies after commit but before the write); Kafka
transactions with exactly-once semantics (only covers Kafka-to-Kafka; the sink here is Postgres, so the database
still has to be idempotent).

## D-003 Stateless consumers: rolling-window history is read back from Postgres

The scorer keeps nothing in memory between batches. For each engine in a batch it reads the previous
`window - 1` readings from Postgres. Any consumer can therefore take over any partition after a rebalance, with
no state store to rebuild. The cost is one extra indexed query per batch, which is small at this scale.
*Alternative:* in-memory windows per engine (faster, but lost on rebalance or restart).

## D-004 Bad messages go to a dead-letter queue, never block the partition

A message that is not JSON or breaks the contract is stored in `dead_letters` and published to
`engine-telemetry.dlq`, and the offset still moves. One poison message cannot stop an engine's stream. The DLQ
publish happens after the database commit, so a crash can publish a dead letter twice (at-least-once). The
database copy is deduplicated by `(topic, partition, offset)`.

## D-005 The event contract is a committed JSON Schema

`contracts/telemetry_event.schema.json` is generated from the Pydantic model. A test fails if they differ, so
any change to the event shape is deliberate and visible in review. `schema_version` is a literal, so a v2 producer
is rejected (into the DLQ) instead of being half-understood.

## D-006 OIDC with Authorization Code + PKCE; roles enforced by the API

The browser gets tokens from Keycloak with Authorization Code + PKCE (a public client, so there is no secret in the
browser). Tokens are kept in session storage. The API validates signature (JWKS), expiry, issuer and audience
(`fleet-api`, added by an audience mapper), then checks realm roles. The UI hides the Acknowledge button from
viewers for usability only; the API returns 403 regardless.
*Alternative:* a backend-for-frontend holding tokens in an HTTP-only cookie. That is stronger against XSS and would
be the next step for production; for a demo it adds a service without changing what is shown.

## D-007 A simple model on FD001

Gradient-boosted trees on 10-cycle rolling means and standard deviations, trained on FD001 (one operating
condition, one fault mode). The point of this repository is the data product around the model. The modelling depth
(per-condition normalisation, conformal intervals, cost-based policy) is in
[cmapss-predictive-maintenance](https://github.com/Max-Isse/cmapss-predictive-maintenance).

## D-008 Replay of NASA test engines, with SYNTHETIC fault injection

The stream is a replay of the 100 FD001 test engines, one cycle per tick. Test engines stop before failure, so the
fleet ends with a realistic mix of healthy, warning and critical engines. 0.5% of messages are corrupted and 1%
are sent twice (rates in `configs/config.yaml`), so the dead-letter and deduplication paths run on every replay.
These faults are synthetic and labelled as such.

## D-010 Window statistics computed directly, not with running sums

The first version used pandas `rolling().mean()/.std()`. These use running sums, so their last-digit
floating-point error depends on how many earlier rows were in the frame. Offline (whole history) and online (only
the last `window` readings) features then differed by about 1e-12. That was enough to flip gradient-boosted tree
splits: `test_incremental_batches_equal_one_big_batch` found 32 of 847 predictions differing, by up to 1.7 cycles.
Features are now computed from each window's own values, so live and batch scoring agree exactly (0 of 847 differ).
*Lesson:* "same code offline and online" is not enough to rule out training/serving skew; the test has to compare
the outputs.

## D-011 A commit rejected by a rebalance is skipped, not fatal

Scaling from one scorer to three triggered a rebalance while a batch was in flight. The synchronous commit then
failed with `ILLEGAL_GENERATION` and the first version crashed and restarted. No data was lost, because the batch
was already committed to Postgres and the restart reprocessed it idempotently, but a normal rebalance should not
crash a consumer. The scorer now commits explicit per-partition offsets for the batch it processed, and on
`ILLEGAL_GENERATION`, `UNKNOWN_MEMBER_ID` or `REBALANCE_IN_PROGRESS` it logs and carries on. The new owner
redelivers from the last committed offset and the upserts absorb the repeat.

## D-009 Risk bands are planning assumptions

Critical below 20 predicted cycles, warning below 50. These are operating thresholds, not estimates, and live in
`configs/config.yaml`.
