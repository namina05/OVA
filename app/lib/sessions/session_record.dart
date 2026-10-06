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

  /// The `session_zones` row for this zone. [zone] is zero-based here and
  /// one-based in the database.
  Map<String, dynamic> toRow({required String sessionId, required int zone}) =>
      {
        'session_id': sessionId,
        'zone': zone + 1,
        'level': level.index,
        'seconds_active': secondsActive,
        'pain_intensity': painIntensity,
        'avg_temp_c': avgTempC,
        'peak_temp_c': peakTempC,
      };

  factory ZoneSummary.fromRow(Map<String, dynamic> row) => ZoneSummary(
    level: HeatLevel.values[row['level'] as int],
    secondsActive: row['seconds_active'] as int,
    painIntensity: row['pain_intensity'] as int?,
    avgTempC: (row['avg_temp_c'] as num?)?.toDouble(),
    peakTempC: (row['peak_temp_c'] as num?)?.toDouble(),
  );
}

/// One use of the belt. Mirrors a `sessions` row plus its zone rows.
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

  /// How many times the user has been asked to rate this session.
  final int reliefPrompts;

  bool get isFinished => endReason != null;

  SessionRecord copyWith({
    List<ZoneSummary>? zones,
    int? actualDurationS,
    EndReason? endReason,
    int? reliefScore,
    String? note,
    int? reliefPrompts,
  }) => SessionRecord(
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

  /// The `sessions` row for this record, owned by [userId].
  Map<String, dynamic> toRow({required String userId}) => {
    'id': id,
    'user_id': userId,
    'started_at': startedAt.toUtc().toIso8601String(),
    'planned_duration_s': plannedDurationS,
    'actual_duration_s': actualDurationS,
    'end_reason': endReason?.dbName,
    'cycle_day': cycleDay,
    'relief_score': reliefScore,
    'note': note,
    'is_simulated': isSimulated,
    'relief_prompts': reliefPrompts,
  };

  List<Map<String, dynamic>> toZoneRows() => [
    for (var zone = 0; zone < zones.length; zone++)
      zones[zone].toRow(sessionId: id, zone: zone),
  ];

  /// Builds a record from a `sessions` row with its `session_zones` rows
  /// embedded under that key.
  factory SessionRecord.fromRow(Map<String, dynamic> row) {
    final endReason = row['end_reason'] as String?;
    final zones = List.filled(
      zoneCount,
      const ZoneSummary(level: HeatLevel.off, secondsActive: 0),
    );
    for (final zoneRow in row['session_zones'] as List? ?? const []) {
      final zone = (zoneRow as Map<String, dynamic>)['zone'] as int;
      zones[zone - 1] = ZoneSummary.fromRow(zoneRow);
    }
    return SessionRecord(
      id: row['id'] as String,
      startedAt: DateTime.parse(row['started_at'] as String).toLocal(),
      plannedDurationS: row['planned_duration_s'] as int,
      actualDurationS: row['actual_duration_s'] as int?,
      endReason: endReason == null
          ? null
          : EndReason.values.firstWhere((reason) => reason.dbName == endReason),
      cycleDay: row['cycle_day'] as int?,
      reliefScore: row['relief_score'] as int?,
      note: row['note'] as String?,
      isSimulated: row['is_simulated'] as bool,
      reliefPrompts: row['relief_prompts'] as int? ?? 0,
      zones: zones,
    );
  }
}
