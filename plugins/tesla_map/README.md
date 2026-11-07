# Tesla map diagnostics and navigation evidence

Default-off read-only plugin (`ExtTeslaMapEnabled`). Card decodes VEH bus 1 / 0x238,
never the AP-PARTY alias. It publishes `tesla.map` at 2 Hz with a 750 ms broker TTL;
the UI also checks the original CAN timestamp (maximum age 1 s). No Params snapshots,
CAN transmit, route ownership or lane permission. The tile shows the map upper-bound
code/value/unit, fork side/distance, fused-limit comparison, type, dependency and age.

The 28 fields follow the paired `tesla_modely_hw4_perception.dbc`. The speed code table
is independently checked against the retained `tesla_can_visualization.py`: code 2 is
7, code 13 is 60, code 25 is 120; codes 0/31 are unknown, 30 unlimited. Branch code 31
is unknown, not 310 m. A displayed bound is not a verified exact legal limit.

Only regular, unconditional, road-matched fresh limits are compared. Units are converted
before comparison. Differences up to one 5-unit step are tolerated; differences of at
least 10 units must persist with continuous fresh observations for 3 s to be CONFLICT.
Missing sides produce SP_ONLY/MAP_ONLY/NONE; lack of map evidence never grants safety.
A fused source not updated for 500 ms stops all automatic wheel ticks.
Both inputs may share an original map source, so agreement is not independent validation.

## Independent consumers

`auto_speed` and `navassist` each ship an identical small `map_data.py` so either can
be installed and used without this diagnostic tile. No sibling imports, switches or
optional-plugin faults affect their data access. Tests enforce byte-identical copies;
update all three copies together. This is shared passive code, not a separate executing
vehicle feature. Each plugin retains its own BOOL master.

Auto Speed only blocks NEW upward wheel ticks during sustained map/fused conflict.
It neither substitutes a map limit nor lowers the target; normal downward adjustment,
physical manual override, resume gesture and existing Panda rules remain authoritative.
A previously sent command cannot be recalled. Map loss clears the comparison and the
existing fused-limit policy resumes; this never clears a driver's manual override.

NavAssist's card publishes `nav.map`; its process adds event-bound `branchEvidence` to
`nav.state`. Three distinct continuous CAN frames, at least 20 m of decreasing branch
distance, matching side and route distance within 40 m yield CONSISTENT. This means
corroboration, not unique junction identity or permission. Both-sided forks, conflicting
side/distance, repeated frames, stale data, route changes and missing navigation stay
unconfirmed. No route maneuver/distance, lamp request, slowdown, native SP/BSM/paint/
road-edge gate or GPIO sound policy is changed. Navigation route guidance remains the
source of direction. Matching loss does not add an unknown-lane veto. Exits are screen
notices only; no new buzzer alert or automatic passing behavior.

## Validation boundaries

Source and synthetic/DBC replay checks only. No device upload, installation, settings
change, restart, firmware compilation/flash or road test. Before relying on the data,
verify actual bus/firmware layout, frame cadence, conditional limits, fork semantics,
unit conversion, close successive exits and real HUD fit on this vehicle. Matching
parameters are conservative initial diagnostic thresholds, not road-validated tuning.
