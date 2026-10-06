import '../belt/belt_models.dart';

/// Why a session ended. [dbName] matches the `sessions.end_reason` column.
enum EndReason {
  completed('completed', 'Completed'),
  userStopped('user_stopped', 'Stopped early'),
  fault('fault', 'Stopped by a fault'),
  connectionLost('connection_lost', 'Interrupted');

  const EndReason(this.dbName, this.label);
  final String dbName;
  final String label;
}

/// How one zone was used in a session. Mirrors a `session_zones` row.
class ZoneSummary {
  const ZoneSummary({
    required this.level,
    required this.secondsActive,
    this.painIntensity,
    this.avgTempC,
    this.peakTempC,
  });

  /// The level held longest during the session.
  final HeatLevel level;
  final int secondsActive;
  final int? painIntensity;
  final double? avgTempC;
  final double? peakTempC;

  Map<String, dynamic> toJson() => {
        'level': level.index,
        'seconds_active': secondsActive,
        'pain_intensity': painIntensity,
        'avg_temp_c': avgTempC,
        'peak_temp_c': peakTempC,
      };

  factory ZoneSummary.fromJson(Map<String, dynamic> json) => ZoneSummary(
        level: HeatLevel.values[json['level'] as int],
        secondsActive: json['seconds_active'] as int,
        painIntensity: json['pain_intensity'] as int?,
        avgTempC: (json['avg_temp_c'] as num?)?.toDouble(),
        peakTempC: (json['peak_temp_c'] as num?)?.toDouble(),
      );
}

/// One use of the belt. Mirrors a `sessions` row plus its zone rows, so a
/// record can be uploaded as-is once sync exists.
class SessionRecord {
  const SessionRecord({
    required this.id,
    required this.startedAt,
    required this.plannedDurationS,
    required this.isSimulated,
    required this.zones,
    this.actualDurationS,
    this.endReason,
    this.cycleDay,
    this.reliefScore,
    this.note,
    this.reliefPrompts = 0,
  });

  final String id;
  final DateTime startedAt;
  final int plannedDurationS;
  final bool isSimulated;
  final List<ZoneSummary> zones;
  final int? actualDurationS;

  /// Null while the session is still running.
  final EndReason? endReason;
  final int? cycleDay;

  /// 1 (no relief) to 5 (full relief); null until the user rates the session.
  final int? reliefScore;
  final String? note;

  /// How many times the user has been asked to rate this session. Local only.
  final int reliefPrompts;

  bool get isFinished => endReason != null;

  SessionRecord copyWith({
    List<ZoneSummary>? zones,
    int? actualDurationS,
    EndReason? endReason,
    int? reliefScore,
    String? note,
    int? reliefPrompts,
  }) =>
      SessionRecord(
        id: id,
        startedAt: startedAt,
        plannedDurationS: plannedDurationS,
        isSimulated: isSimulated,
        cycleDay: cycleDay,
        zones: zones ?? this.zones,
        actualDurationS: actualDurationS ?? this.actualDurationS,
        endReason: endReason ?? this.endReason,
        reliefScore: reliefScore ?? this.reliefScore,
        note: note ?? this.note,
        reliefPrompts: reliefPrompts ?? this.reliefPrompts,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'started_at': startedAt.toUtc().toIso8601String(),
        'planned_duration_s': plannedDurationS,
        'actual_duration_s': actualDurationS,
        'end_reason': endReason?.dbName,
        'cycle_day': cycleDay,
        'relief_score': reliefScore,
        'note': note,
        'is_simulated': isSimulated,
        'relief_prompts': reliefPrompts,
        'zones': [for (final zone in zones) zone.toJson()],
      };

  factory SessionRecord.fromJson(Map<String, dynamic> json) {
    final endReason = json['end_reason'] as String?;
    return SessionRecord(
      id: json['id'] as String,
      startedAt: DateTime.parse(json['started_at'] as String).toLocal(),
      plannedDurationS: json['planned_duration_s'] as int,
      actualDurationS: json['actual_duration_s'] as int?,
      endReason: endReason == null
          ? null
          : EndReason.values.firstWhere((reason) => reason.dbName == endReason),
      cycleDay: json['cycle_day'] as int?,
      reliefScore: json['relief_score'] as int?,
      note: json['note'] as String?,
      isSimulated: json['is_simulated'] as bool,
      reliefPrompts: json['relief_prompts'] as int? ?? 0,
      zones: [
        for (final zone in json['zones'] as List)
          ZoneSummary.fromJson(zone as Map<String, dynamic>),
      ],
    );
  }
}
