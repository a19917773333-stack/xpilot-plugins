# CP8 withdrawal / observation clock compatibility (1.2.2)

The real CP8 phone sent a valid vehicle observation, an absent envelope, then a
newer GPS observation acquired 77 ms before the administrative withdrawal time.
The old receiver compared the new GPS timestamp against the withdrawal timestamp
and rejected the observation as source_time_regression, closing that JSON stream.

The receiver now keeps a separate watermark for actual present observations.
Withdrawals clear the value without advancing the sensor watermark. Restoring
presence after a withdrawal requires a strictly newer sensor observation; an
identical or older observation cannot revive a withdrawn value. Normal present
heartbeats may repeat an observation but cannot extend its source expiry.

Session/stream binding, strictly advancing transport sequence numbers, the
1500 ms source-age budget, 500 ms future bound and send-time checks are unchanged.
Watermarks reset with their bound session. No control or camera flags are changed.

Validation: 11 regression cases were recorded before the implementation (the
old receiver failed 3); all 558 plugin checks pass. Replaying 52 real phone
envelopes across 2 sessions changes acceptance from 51/52 to 52/52. Raw captures,
locations and APKs remain private and are not included here. This does not claim
that every possible stale/replay rejection is resolved, that CP-native vehicle
policy is migrated, or that onroad behavior has been validated.
