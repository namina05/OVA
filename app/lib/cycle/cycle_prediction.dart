import 'period.dart';

/// A health alert the backend raised from the user's cycle pattern.
class CycleAlert {
  const CycleAlert({required this.title, required this.advice});

  factory CycleAlert.fromJson(Map<String, dynamic> json) => CycleAlert(
    title: json['trigger_label'] as String,
    advice: json['advice'] as String,
  );

  final String title;
  final String advice;
}

/// The backend's forecast of the next period (`POST /cycle/predict`).
class CyclePrediction {
  const CyclePrediction({
    required this.predictedStart,
    required this.rangeDays,
    required this.predictedPeriodLength,
    required this.daysUntilStart,
    required this.isLate,
    required this.explanation,
    required this.notice,
    this.ovulationDate,
    this.fertileStart,
    this.fertileEnd,
    this.highPainDates = const [],
    this.alerts = const [],
  });

  factory CyclePrediction.fromJson(Map<String, dynamic> json) =>
      CyclePrediction(
        predictedStart: DateTime.parse(json['predicted_start'] as String),
        rangeDays: json['range_days'] as int,
        predictedPeriodLength: json['predicted_period_length'] as int,
        daysUntilStart: json['days_until_start'] as int,
        isLate: json['is_late'] as bool,
        explanation: json['explanation'] as String,
        notice: json['notice'] as String,
        ovulationDate: _date(json['ovulation_date']),
        fertileStart: _date(json['fertile_start']),
        fertileEnd: _date(json['fertile_end']),
        highPainDates: [
          for (final date in json['high_pain_dates'] as List)
            DateTime.parse(date as String),
        ],
        alerts: [
          for (final alert in json['health_alerts'] as List)
            CycleAlert.fromJson(alert as Map<String, dynamic>),
        ],
      );

  final DateTime predictedStart;

  /// The start is expected within this many days either side.
  final int rangeDays;
  final int predictedPeriodLength;

  /// Negative once the predicted start has passed.
  final int daysUntilStart;
  final bool isLate;

  /// How the backend arrived at the date, in plain words.
  final String explanation;

  /// The backend's reminder of what a prediction cannot be used for.
  final String notice;

  /// The backend's estimate of ovulation in the current cycle, and the days
  /// around it when pregnancy is most likely. Null when it cannot estimate.
  final DateTime? ovulationDate;
  final DateTime? fertileStart;
  final DateTime? fertileEnd;

  /// Days of the predicted period expected to be the most painful.
  final List<DateTime> highPainDates;
  final List<CycleAlert> alerts;

  /// Every day of the estimated fertile window.
  Set<DateTime> get fertileDays {
    final start = fertileStart, end = fertileEnd;
    if (start == null || end == null) return const {};
    return {
      for (var day = start; !day.isAfter(end); day = addDays(day, 1)) day,
    };
  }

  /// Every day of the predicted period.
  Set<DateTime> get days => {
    for (var i = 0; i < predictedPeriodLength; i++) addDays(predictedStart, i),
  };
}

DateTime? _date(Object? value) =>
    value == null ? null : DateTime.parse(value as String);
