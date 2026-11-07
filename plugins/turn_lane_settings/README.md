# Turn & Lane Settings

Open **Plugins -> Turn & Lane Settings** while parked. The optional master switch shows a parked summary tile; it does not change or override saved SP control settings.

The native parked-only setting rows edit the existing compiled `LaneTurnDesire`, `LaneTurnValue` (stored in mph, labelled in km/h), and `AutoLaneChangeTimer` parameters. They deliberately are NOT redeclared as plugin params: doing so would shadow real SP values. No vehicle-control hook, CAN message, process, model, or firmware change. Installing/enabling/disabling/removing the panel does not change these values. The current SP controller caps turn-intent speed at 20 mph (about 32.2 km/h); the panel does not bypass that cap. Actual single-blinker feedback and existing SP safety checks remain necessary.
