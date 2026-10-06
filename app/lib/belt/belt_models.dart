/// Number of heating zones on the belt.
const int zoneCount = 4;

/// Zone names in belt order, as the wearer sees them.
const zoneNames = ['Upper left', 'Upper right', 'Lower left', 'Lower right'];

/// Heat level of one zone. The index is the byte sent over Bluetooth.
enum HeatLevel {
  off('Off'),
  low('Low'),
  medium('Med'),
  high('High');

  const HeatLevel(this.label);
  final String label;
}

enum SessionState { idle, running, paused }

enum FaultCode { overTemperature, sensorFailure, lowBattery, rejectedCommand }

/// What the belt reports about itself. The app must stay inside these limits.
class BeltInfo {
  const BeltInfo({
    required this.firmwareVersion,
    required this.levelTargetsC,
    required this.maxSession,
  });

  final String firmwareVersion;

  /// Target temperature for each non-off [HeatLevel].
  final Map<HeatLevel, double> levelTargetsC;
  final Duration maxSession;
}

/// One telemetry frame, sent by the belt once per second.
class BeltTelemetry {
  const BeltTelemetry({
    required this.zoneTempsC,
    required this.zoneLevels,
    required this.state,
    required this.remaining,
  });

  final List<double> zoneTempsC;
  final List<HeatLevel> zoneLevels;
  final SessionState state;
  final Duration remaining;
}

class BeltFault {
  const BeltFault(this.code, {this.zone});

  final FaultCode code;

  /// Zero-based zone index, or null when the fault is not zone-specific.
  final int? zone;
}

/// Thrown when the belt rejects a command.
class BeltException implements Exception {
  const BeltException(this.message);
  final String message;

  @override
  String toString() => 'BeltException: $message';
}
