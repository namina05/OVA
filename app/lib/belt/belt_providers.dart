import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'belt_device.dart';
import 'belt_models.dart';
import 'simulated_belt.dart';

/// The connected belt. Swap the body for the BLE implementation once the
/// hardware is ready; nothing else in the app needs to change.
final beltProvider = Provider<BeltDevice>((ref) {
  final belt = SimulatedBelt();
  ref.onDispose(belt.dispose);
  return belt;
});

final beltInfoProvider = FutureProvider<BeltInfo>((ref) {
  return ref.watch(beltProvider).readInfo();
});

final beltTelemetryProvider = StreamProvider<BeltTelemetry>((ref) {
  return ref.watch(beltProvider).telemetry;
});
