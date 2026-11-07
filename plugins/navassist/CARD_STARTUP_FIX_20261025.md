# Car interface startup recovery (1.2.3)

The real onroad card process crashed while serializing CarParamsSP. NavAssist's
Panda feature flag 0x8000 OR'ed with the OEM flags 3 produced Python integer
32771, outside the schema field's signed Int16 range.

setup now encodes the same 16 bits as a signed two's-complement integer. For
0x8003 the schema value is -32765. The existing pandad consumer reads that field
into uint16_t, recovering exactly 0x8003. No feature bit is removed, no Panda
check is bypassed, and neither schema nor firmware is changed. The vehicle-bus
harness gate and all lower OEM bits remain intact; repeated setup is idempotent.

Eight real-schema regression cases were written before the change; the old code
failed five. They round-trip through the actual CarParamsSP serializer and verify
the Panda uint16 bit pattern. All 566 plugin tests pass after the correction.
Device-side serialization and actual post-ignition startup are separate checks.
The plugin was temporarily disabled during recovery. Native CP decision parity
and complete phone-app parity remain unfinished and are not implied by this fix.
