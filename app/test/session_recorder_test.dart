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
    recorder = SessionRecorder(
      belt: belt,
      repository: repository,
      now: () => startTime,
    )..start();
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
    await belt.setZoneLevels([
      HeatLevel.high,
      HeatLevel.off,
      HeatLevel.low,
      HeatLevel.off,
    ]);
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

  test(
    'paused time is not counted, and stopping while paused is a user stop',
    () async {
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
    },
  );

  test('a zone records the level it was held at longest', () async {
    await belt.setZoneLevels([
      HeatLevel.low,
      HeatLevel.off,
      HeatLevel.off,
      HeatLevel.off,
    ]);
    await belt.start(const Duration(seconds: 60));
    await tick(10);
    await belt.setZoneLevels([
      HeatLevel.high,
      HeatLevel.off,
      HeatLevel.off,
      HeatLevel.medium,
    ]);
    await tick(50);

    final session = (await repository.all()).single;
    expect(session.zones[0].level, HeatLevel.high);
    expect(session.zones[0].secondsActive, 60);
    expect(session.zones[3].level, HeatLevel.medium);
    expect(session.zones[3].secondsActive, 50);
  });

  test(
    'a running session is already saved, and is closed on the next launch',
    () async {
      await belt.setZoneLevels(List.filled(zoneCount, HeatLevel.high));
      await belt.start(const Duration(minutes: 20));
      await tick(25);

      final running = (await repository.all()).single;
      expect(running.isFinished, isFalse);
      expect(running.actualDurationS, 20);

      // Simulate the app being killed and reopened: same storage, new objects.
      final reopened = SessionRepository(store);
      final nextBelt = SimulatedBelt(autoTick: false);
      final nextRecorder = SessionRecorder(belt: nextBelt, repository: reopened)
        ..start();
      await nextRecorder.ready;

      final recovered = (await reopened.all()).single;
      expect(recovered.id, running.id);
      expect(recovered.endReason, EndReason.connectionLost);
      expect(recovered.actualDurationS, 20);

      await nextRecorder.dispose();
      await nextBelt.dispose();
    },
  );

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

  test('a record survives the trip to database rows and back', () {
    final record = SessionRecord(
      id: 'abc',
      startedAt: startTime,
      plannedDurationS: 600,
      actualDurationS: 590,
      endReason: EndReason.userStopped,
      reliefScore: 4,
      note: 'Helped a lot',
      isSimulated: false,
      reliefPrompts: 1,
      zones: const [
        ZoneSummary(
          level: HeatLevel.high,
          secondsActive: 590,
          avgTempC: 41.2,
          peakTempC: 42,
        ),
        ZoneSummary(level: HeatLevel.off, secondsActive: 0),
        ZoneSummary(level: HeatLevel.off, secondsActive: 0),
        ZoneSummary(level: HeatLevel.low, secondsActive: 300, painIntensity: 7),
      ],
    );

    final sessionRow = record.toRow(userId: 'user-1');
    final zoneRows = record.toZoneRows();
    expect(sessionRow['user_id'], 'user-1');
    expect(sessionRow['end_reason'], 'user_stopped');
    expect(sessionRow.containsKey('zones'), isFalse);
    expect(zoneRows.map((row) => row['zone']), [1, 2, 3, 4]);
    expect(zoneRows.every((row) => row['session_id'] == 'abc'), isTrue);

    // The database returns zone rows embedded, in no particular order.
    final reread = SessionRecord.fromRow({
      ...sessionRow,
      'session_zones': zoneRows.reversed.toList(),
    });
    expect(reread.toRow(userId: 'user-1'), sessionRow);
    expect(reread.toZoneRows(), zoneRows);
    expect(reread.startedAt, startTime);
  });

  test('a session whose zone rows never arrived still loads', () {
    final reread = SessionRecord.fromRow({
      'id': 'abc',
      'started_at': '2026-10-06T11:30:00Z',
      'planned_duration_s': 600,
      'is_simulated': true,
      'session_zones': [
        {
          'zone': 3,
          'level': 2,
          'seconds_active': 40,
          'avg_temp_c': 39,
          'peak_temp_c': 39.8,
        },
      ],
    });
    expect(reread.zones, hasLength(zoneCount));
    expect(reread.zones[2].level, HeatLevel.medium);
    expect(reread.zones[2].avgTempC, 39.0);
    expect(reread.zones[0].secondsActive, 0);
    expect(reread.isFinished, isFalse);
  });

  group('when the store cannot be reached', () {
    SessionRecord sample(String id, {int? reliefScore}) => SessionRecord(
      id: id,
      startedAt: startTime,
      plannedDurationS: 60,
      actualDurationS: 60,
      endReason: EndReason.completed,
      reliefScore: reliefScore,
      isSimulated: true,
      zones: List.filled(
        zoneCount,
        const ZoneSummary(level: HeatLevel.off, secondsActive: 0),
      ),
    );

    test(
      'saves show in the app at once and are sent when it is reachable again',
      () async {
        store.offline = true;
        await repository.save(sample('a'));
        await repository.save(sample('a', reliefScore: 5));

        expect((await repository.all()).single.reliefScore, 5);
        expect(repository.hasUnsentChanges, isTrue);
        expect(store.records, isEmpty);

        store.offline = false;
        await repository.all();
        expect(repository.hasUnsentChanges, isFalse);
        expect(store.records['a']!.reliefScore, 5);
      },
    );

    test('a delete made offline is carried out later', () async {
      await repository.save(sample('a'));
      store.offline = true;
      await repository.delete('a');
      expect(await repository.all(), isEmpty);
      expect(store.records, contains('a'));

      store.offline = false;
      await repository.all();
      expect(store.records, isEmpty);
    });

    test(
      'sessions already stored appear once it is reachable, without undoing local changes',
      () async {
        store.records['old'] = sample('old');
        store.records['a'] = sample('a', reliefScore: 1);
        store.offline = true;
        final fresh = SessionRepository(store);
        await fresh.save(sample('a', reliefScore: 4));
        expect(await fresh.all(), hasLength(1));

        store.offline = false;
        final sessions = await fresh.all();
        expect(sessions.map((s) => s.id), unorderedEquals(['old', 'a']));
        expect(sessions.firstWhere((s) => s.id == 'a').reliefScore, 4);
        expect(store.records['a']!.reliefScore, 4);
      },
    );
  });
}
