import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:ova/belt/belt_models.dart';
import 'package:ova/belt/simulated_belt.dart';
import 'package:ova/sessions/session_record.dart';
import 'package:ova/sessions/session_recorder.dart';
import 'package:ova/sessions/session_repository.dart';

void main() {
  late SimulatedBelt belt;
  late MemorySessionStore store;
  late SessionRepository repository;
  late SessionRecorder recorder;
  late List<SessionRecord> ended;

  final startTime = DateTime(2026, 10, 6, 17);

  setUp(() async {
    belt = SimulatedBelt(autoTick: false);
    store = MemorySessionStore();
    repository = SessionRepository(store);
    recorder = SessionRecorder(belt: belt, repository: repository, now: () => startTime)..start();
    ended = [];
    recorder.ended.listen(ended.add);
    await recorder.ready;
  });

  tearDown(() async {
    await recorder.dispose();
    await belt.dispose();
  });

  Future<void> tick(int seconds) async {
    for (var i = 0; i < seconds; i++) {
      belt.tick();
      await Future<void>.delayed(Duration.zero);
    }
    await Future<void>.delayed(Duration.zero);
  }

  test('logs a session that runs to the end of its timer', () async {
    await belt.setZoneLevels([HeatLevel.high, HeatLevel.off, HeatLevel.low, HeatLevel.off]);
    await belt.start(const Duration(seconds: 120));
    await tick(120);

    final session = (await repository.all()).single;
    expect(ended.single.id, session.id);
    expect(session.endReason, EndReason.completed);
    expect(session.startedAt, startTime);
    expect(session.plannedDurationS, 120);
    expect(session.actualDurationS, 120);
    expect(session.isSimulated, isTrue);
    expect(session.reliefScore, isNull);

    expect(session.zones[0].level, HeatLevel.high);
    expect(session.zones[0].secondsActive, 120);
    expect(session.zones[0].avgTempC, inInclusiveRange(38, 42));
    expect(session.zones[0].peakTempC, closeTo(42, 0.1));

    expect(session.zones[1].level, HeatLevel.off);
    expect(session.zones[1].secondsActive, 0);
    expect(session.zones[1].avgTempC, isNull);

    expect(session.zones[2].level, HeatLevel.low);
    expect(session.zones[2].peakTempC, closeTo(38, 0.1));
  });

  test('a session stopped by the user records the time actually run', () async {
    await belt.setZoneLevels(List.filled(zoneCount, HeatLevel.medium));
    await belt.start(const Duration(minutes: 20));
    await tick(45);
    await belt.stop();
    await tick(0);

    final session = (await repository.all()).single;
    expect(session.endReason, EndReason.userStopped);
    expect(session.plannedDurationS, 1200);
    expect(session.actualDurationS, 45);
    expect(session.zones[0].secondsActive, 45);
  });

  test('paused time is not counted, and stopping while paused is a user stop', () async {
    await belt.setZoneLevels(List.filled(zoneCount, HeatLevel.low));
    await belt.start(const Duration(minutes: 5));
    await tick(20);
    await belt.pause();
    await tick(60);
    await belt.resume();
    await tick(10);
    await belt.pause();
    await belt.stop();
    await tick(0);

    final session = (await repository.all()).single;
    expect(session.endReason, EndReason.userStopped);
    expect(session.actualDurationS, 30);
    expect(session.zones[0].secondsActive, 30);
  });

  test('a zone records the level it was held at longest', () async {
    await belt.setZoneLevels([HeatLevel.low, HeatLevel.off, HeatLevel.off, HeatLevel.off]);
    await belt.start(const Duration(seconds: 60));
    await tick(10);
    await belt.setZoneLevels([HeatLevel.high, HeatLevel.off, HeatLevel.off, HeatLevel.medium]);
    await tick(50);

    final session = (await repository.all()).single;
    expect(session.zones[0].level, HeatLevel.high);
    expect(session.zones[0].secondsActive, 60);
    expect(session.zones[3].level, HeatLevel.medium);
    expect(session.zones[3].secondsActive, 50);
  });

  test('a running session is already saved, and is closed on the next launch', () async {
    await belt.setZoneLevels(List.filled(zoneCount, HeatLevel.high));
    await belt.start(const Duration(minutes: 20));
    await tick(25);

    final running = (await repository.all()).single;
    expect(running.isFinished, isFalse);
    expect(running.actualDurationS, 20);

    // Simulate the app being killed and reopened: same storage, new objects.
    final reopened = SessionRepository(store);
    final nextBelt = SimulatedBelt(autoTick: false);
    final nextRecorder = SessionRecorder(belt: nextBelt, repository: reopened)..start();
    await nextRecorder.ready;

    final recovered = (await reopened.all()).single;
    expect(recovered.id, running.id);
    expect(recovered.endReason, EndReason.connectionLost);
    expect(recovered.actualDurationS, 20);

    await nextRecorder.dispose();
    await nextBelt.dispose();
  });

  test('two sessions in a row are logged separately, newest first', () async {
    await belt.setZoneLevels(List.filled(zoneCount, HeatLevel.low));
    await belt.start(const Duration(seconds: 5));
    await tick(5);
    await belt.start(const Duration(seconds: 8));
    await tick(8);

    final sessions = await repository.all();
    expect(sessions, hasLength(2));
    expect(sessions.map((s) => s.plannedDurationS), unorderedEquals([5, 8]));
    expect(sessions.every((s) => s.endReason == EndReason.completed), isTrue);
  });

  test('the log survives being written to and read back from a file', () async {
    final directory = await Directory.systemTemp.createTemp('ova_sessions');
    addTearDown(() => directory.delete(recursive: true));
    final file = File('${directory.path}/sessions.json');

    final onDisk = SessionRepository(FileSessionStore(() async => file));
    final record = SessionRecord(
      id: 'abc',
      startedAt: startTime,
      plannedDurationS: 600,
      actualDurationS: 590,
      endReason: EndReason.userStopped,
      reliefScore: 4,
      note: 'Helped a lot',
      isSimulated: false,
      zones: const [
        ZoneSummary(level: HeatLevel.high, secondsActive: 590, avgTempC: 41.2, peakTempC: 42),
        ZoneSummary(level: HeatLevel.off, secondsActive: 0),
        ZoneSummary(level: HeatLevel.off, secondsActive: 0),
        ZoneSummary(level: HeatLevel.low, secondsActive: 300, painIntensity: 7),
      ],
    );
    await onDisk.save(record);
    await onDisk.save(record.copyWith(reliefPrompts: 1));

    final reread = (await SessionRepository(FileSessionStore(() async => file)).all()).single;
    expect(reread.toJson(), record.copyWith(reliefPrompts: 1).toJson());
    expect(reread.startedAt, startTime);
    expect(File('${file.path}.tmp').existsSync(), isFalse);

    await onDisk.delete('abc');
    expect(await SessionRepository(FileSessionStore(() async => file)).all(), isEmpty);
  });
}
