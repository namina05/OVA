import 'belt_models.dart';

/// The app's only view of the belt. Mirrors the Bluetooth contract in SRS
/// section 3.2, so the real BLE implementation and [SimulatedBelt] are
/// interchangeable.
abstract interface class BeltDevice {
  Future<BeltInfo> readInfo();

  /// Sets the level of every zone. [levels] must have [zoneCount] entries.
  Future<void> setZoneLevels(List<HeatLevel> levels);

  Future<void> start(Duration duration);
  Future<void> pause();
  Future<void> resume();
  Future<void> stop();

  Stream<BeltTelemetry> get telemetry;
  Stream<BeltFault> get faults;

  /// Battery charge, 0 to 100.
  Stream<int> get battery;

  Future<void> dispose();
}
