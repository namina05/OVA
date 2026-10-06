import 'dart:async';
import 'dart:math';

import 'package:uuid/uuid.dart';

import '../belt/belt_device.dart';
import '../belt/belt_models.dart';
import 'session_record.dart';
import 'session_repository.dart';

/// Watches the belt and writes a [SessionRecord] for every session, with no
/// action needed from the user (SRS FR-LOG-1).
class SessionRecorder {
  SessionRecorder({
    required BeltDevice belt,
    required SessionRepository repository,
    DateTime Function() now = DateTime.now,
  }) : _belt = belt,
       _repository = repository,
       _now = now;

  /// A running session is saved this often, so little is lost if the app is
  /// killed mid-session (SRS NFR-REL-2).
  static const int _saveEveryS = 10;

  final BeltDevice _belt;
  final SessionRepository _repository;
  final DateTime Function() _now;
  final _ended = StreamController<SessionRecord>.broadcast();

  StreamSubscription<BeltTelemetry>? _subscription;
  BeltTelemetry? _lastFrame;
  SessionRecord? _current;
  List<_ZoneTally> _tallies = [];
  int _elapsedS = 0;
  int _savedAtS = 0;

  /// Emits each session as it finishes.
  Stream<SessionRecord> get ended => _ended.stream;

  /// Completes once sessions left unfinished by an earlier run are closed.
  late final Future<void> ready;

  void start() {
    _subscription = _belt.telemetry.listen(_onFrame);
    ready = _closeInterrupted();
  }

  Future<void> dispose() async {
    await _subscription?.cancel();
    await _ended.close();
  }

  /// A record with no end reason and no live session behind it means the app
  /// was killed mid-session.
  Future<void> _closeInterrupted() async {
    for (final record in await _repository.all()) {
      if (!record.isFinished && record.id != _current?.id) {
        await _repository.save(
          record.copyWith(endReason: EndReason.connectionLost),
        );
      }
    }
  }

  void _onFrame(BeltTelemetry frame) {
    final previous = _lastFrame;
    _lastFrame = frame;

    if (_current == null) {
      if (frame.state == SessionState.running) _begin(frame);
      return;
    }

    // The belt reports no end reason, so infer it: a session that goes idle
    // with time still on the clock was stopped by the user.
    var stoppedEarly = previous!.state == SessionState.paused;
    if (previous.state == SessionState.running) {
      if (frame.state == SessionState.idle &&
          previous.remaining > const Duration(seconds: 1)) {
        stoppedEarly = true;
      } else {
        final seconds = (previous.remaining - frame.remaining).inSeconds;
        if (seconds > 0) _tally(previous.zoneLevels, frame.zoneTempsC, seconds);
      }
    }
    for (var zone = 0; zone < zoneCount; zone++) {
      _tallies[zone].peakTempC = max(
        _tallies[zone].peakTempC,
        frame.zoneTempsC[zone],
      );
    }

    if (frame.state == SessionState.idle) {
      _finish(stoppedEarly ? EndReason.userStopped : EndReason.completed);
    } else if (_elapsedS - _savedAtS >= _saveEveryS) {
      _save();
    }
  }

  void _begin(BeltTelemetry frame) {
    _tallies = [
      for (var zone = 0; zone < zoneCount; zone++)
        _ZoneTally(frame.zoneTempsC[zone]),
    ];
    _elapsedS = 0;
    _current = SessionRecord(
      id: const Uuid().v4(),
      startedAt: _now(),
      plannedDurationS: frame.remaining.inSeconds,
      isSimulated: _belt.isSimulated,
      zones: _summaries(frame.zoneLevels),
    );
    _save();
  }

  void _tally(List<HeatLevel> levels, List<double> tempsC, int seconds) {
    _elapsedS += seconds;
    for (var zone = 0; zone < zoneCount; zone++) {
      final tally = _tallies[zone];
      tally.secondsAtLevel[levels[zone]] =
          (tally.secondsAtLevel[levels[zone]] ?? 0) + seconds;
      if (levels[zone] != HeatLevel.off) {
        tally.secondsActive += seconds;
        tally.tempSecondsC += tempsC[zone] * seconds;
      }
    }
  }

  SessionRecord _snapshot() => _current!.copyWith(
    actualDurationS: _elapsedS,
    zones: _summaries(_lastFrame!.zoneLevels),
  );

  void _save() {
    _savedAtS = _elapsedS;
    _current = _snapshot();
    _repository.save(_current!);
  }

  void _finish(EndReason reason) {
    final finished = _snapshot().copyWith(endReason: reason);
    _current = null;
    _repository.save(finished);
    _ended.add(finished);
  }

  List<ZoneSummary> _summaries(List<HeatLevel> currentLevels) => [
    for (var zone = 0; zone < zoneCount; zone++)
      _tallies[zone].summarise(fallbackLevel: currentLevels[zone]),
  ];
}

class _ZoneTally {
  _ZoneTally(this.peakTempC);

  final Map<HeatLevel, int> secondsAtLevel = {};
  int secondsActive = 0;

  /// Sum of temperature × seconds while the zone was heating.
  double tempSecondsC = 0;
  double peakTempC;

  ZoneSummary summarise({required HeatLevel fallbackLevel}) {
    var level = fallbackLevel;
    var longest = 0;
    secondsAtLevel.forEach((candidate, seconds) {
      if (seconds > longest) {
        level = candidate;
        longest = seconds;
      }
    });
    return ZoneSummary(
      level: level,
      secondsActive: secondsActive,
      avgTempC: secondsActive == 0
          ? null
          : _round(tempSecondsC / secondsActive),
      peakTempC: _round(peakTempC),
    );
  }

  static double _round(double value) => (value * 10).round() / 10;
}
