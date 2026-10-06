import 'package:flutter_test/flutter_test.dart';
import 'package:ova/belt/belt_models.dart';
import 'package:ova/belt/simulated_belt.dart';

void main() {
  late SimulatedBelt belt;
  late BeltTelemetry last;

  setUp(() {
    belt = SimulatedBelt(autoTick: false);
    belt.telemetry.listen((frame) => last = frame);
  });

  tearDown(() => belt.dispose());

  Future<void> tick(int seconds) async {
    for (var i = 0; i < seconds; i++) {
      belt.tick();
    }
    await Future<void>.delayed(Duration.zero);
  }

  test('heated zones approach their target and never exceed it', () async {
    await belt.setZoneLevels(
        [HeatLevel.high, HeatLevel.off, HeatLevel.low, HeatLevel.off]);
    await belt.start(const Duration(minutes: 10));
    await tick(300);

    expect(last.zoneTempsC[0], closeTo(42, 0.1));
    expect(last.zoneTempsC[0], lessThanOrEqualTo(42));
    expect(last.zoneTempsC[2], closeTo(38, 0.1));
    expect(last.zoneTempsC[1], closeTo(32, 0.1));
  });

  test('zones do not heat before a session starts', () async {
    await belt.setZoneLevels(List.filled(zoneCount, HeatLevel.high));
    await tick(60);

    expect(last.state, SessionState.idle);
    expect(last.zoneTempsC, everyElement(closeTo(32, 0.1)));
  });

  test('session ends on its own when the timer runs out, then cools', () async {
    await belt.setZoneLevels(List.filled(zoneCount, HeatLevel.medium));
    await belt.start(const Duration(seconds: 30));
    await tick(29);
    expect(last.state, SessionState.running);
    expect(last.remaining, const Duration(seconds: 1));

    await tick(1);
    expect(last.state, SessionState.idle);
    final tempAtEnd = last.zoneTempsC[0];

    await tick(60);
    expect(last.zoneTempsC[0], lessThan(tempAtEnd));
  });

  test('pause holds the timer and resume continues it', () async {
    await belt.setZoneLevels(List.filled(zoneCount, HeatLevel.low));
    await belt.start(const Duration(minutes: 5));
    await tick(10);
    await belt.pause();
    await tick(30);
    expect(last.state, SessionState.paused);
    expect(last.remaining, const Duration(minutes: 4, seconds: 50));

    await belt.resume();
    await tick(10);
    expect(last.remaining, const Duration(minutes: 4, seconds: 40));
  });

  test('stop ends the session immediately', () async {
    await belt.setZoneLevels(List.filled(zoneCount, HeatLevel.high));
    await belt.start(const Duration(minutes: 5));
    await tick(5);
    await belt.stop();
    await tick(0);

    expect(last.state, SessionState.idle);
    expect(last.remaining, Duration.zero);
  });

  test('rejects a session longer than the belt allows and reports a fault',
      () async {
    final faults = <BeltFault>[];
    belt.faults.listen(faults.add);

    await expectLater(
      belt.start(SimulatedBelt.info.maxSession + const Duration(seconds: 1)),
      throwsA(isA<BeltException>()),
    );
    await tick(1);

    expect(faults.single.code, FaultCode.rejectedCommand);
    expect(last.state, SessionState.idle);
  });

  test('rejects the wrong number of zone levels', () async {
    await expectLater(
      belt.setZoneLevels([HeatLevel.low]),
      throwsA(isA<BeltException>()),
    );
  });
}
