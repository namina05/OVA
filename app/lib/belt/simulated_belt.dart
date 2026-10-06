import 'dart:async';

import 'belt_device.dart';
import 'belt_models.dart';

/// A software stand-in for the belt (SRS HW-4). It enforces the same limits
/// the firmware will, and warms each zone toward its target a little every
/// second.
class SimulatedBelt implements BeltDevice {
  /// With [autoTick] false nothing advances until [tick] is called, which
  /// lets tests step time by hand.
  SimulatedBelt({bool autoTick = true}) {
    if (autoTick) {
      _timer = Timer.periodic(const Duration(seconds: 1), (_) => tick());
    }
  }

  static const BeltInfo info = BeltInfo(
    firmwareVersion: 'sim-0.1',
    levelTargetsC: {
      HeatLevel.low: 38,
      HeatLevel.medium: 40,
      HeatLevel.high: 42,
    },
    maxSession: Duration(minutes: 45),
  );

  static const double _restingTempC = 32;

  /// Fraction of the gap to the target closed each second.
  static const double _warmRate = 0.08;

  final _telemetry = StreamController<BeltTelemetry>.broadcast();
  final _faults = StreamController<BeltFault>.broadcast();
  final _battery = StreamController<int>.broadcast();

  Timer? _timer;
  List<HeatLevel> _levels = List.filled(zoneCount, HeatLevel.off);
  final List<double> _temps = List.filled(zoneCount, _restingTempC);
  SessionState _state = SessionState.idle;
  Duration _remaining = Duration.zero;

  @override
  bool get isSimulated => true;

  @override
  Stream<BeltTelemetry> get telemetry => _telemetry.stream;

  @override
  Stream<BeltFault> get faults => _faults.stream;

  @override
  Stream<int> get battery => _battery.stream;

  @override
  Future<BeltInfo> readInfo() async => info;

  @override
  Future<void> setZoneLevels(List<HeatLevel> levels) async {
    if (levels.length != zoneCount) {
      _reject('Expected $zoneCount zone levels, got ${levels.length}');
    }
    _levels = List.of(levels);
    _emit();
  }

  @override
  Future<void> start(Duration duration) async {
    if (duration <= Duration.zero || duration > info.maxSession) {
      _reject(
        'Duration must be between 1 second and ${info.maxSession.inMinutes} minutes',
      );
    }
    _remaining = duration;
    _state = SessionState.running;
    _emit();
  }

  @override
  Future<void> pause() async {
    if (_state != SessionState.running) return;
    _state = SessionState.paused;
    _emit();
  }

  @override
  Future<void> resume() async {
    if (_state != SessionState.paused) return;
    _state = SessionState.running;
    _emit();
  }

  @override
  Future<void> stop() async {
    _state = SessionState.idle;
    _remaining = Duration.zero;
    _emit();
  }

  /// Advances the simulation by one second.
  void tick() {
    if (_state == SessionState.running) {
      _remaining -= const Duration(seconds: 1);
      if (_remaining <= Duration.zero) {
        _remaining = Duration.zero;
        _state = SessionState.idle;
      }
    }
    for (var zone = 0; zone < zoneCount; zone++) {
      final heating =
          _state == SessionState.running && _levels[zone] != HeatLevel.off;
      final target = heating
          ? info.levelTargetsC[_levels[zone]]!
          : _restingTempC;
      _temps[zone] += (target - _temps[zone]) * _warmRate;
    }
    _emit();
    _battery.add(100);
  }

  @override
  Future<void> dispose() async {
    _timer?.cancel();
    await _telemetry.close();
    await _faults.close();
    await _battery.close();
  }

  void _emit() {
    _telemetry.add(
      BeltTelemetry(
        zoneTempsC: List.unmodifiable(_temps),
        zoneLevels: List.unmodifiable(_levels),
        state: _state,
        remaining: _remaining,
      ),
    );
  }

  Never _reject(String message) {
    _faults.add(const BeltFault(FaultCode.rejectedCommand));
    throw BeltException(message);
  }
}
