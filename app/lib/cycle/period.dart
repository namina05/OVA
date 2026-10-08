/// One logged period: one row of `periods`.
class Period {
  const Period({this.id, required this.startDate, this.endDate});

  factory Period.fromRow(Map<String, dynamic> row) => Period(
    id: row['id'] as String,
    startDate: DateTime.parse(row['start_date'] as String),
    endDate: row['end_date'] == null
        ? null
        : DateTime.parse(row['end_date'] as String),
  );

  /// Null until the period has been stored.
  final String? id;

  /// Calendar dates; the time of day is not used.
  final DateTime startDate;

  /// The last day of bleeding. Null while the period is still going.
  final DateTime? endDate;

  /// Days of bleeding, counting the first and last. Null while ongoing.
  int? get lengthDays =>
      endDate == null ? null : daysBetween(startDate, endDate!) + 1;

  Map<String, dynamic> toRow({required String userId}) => {
    'user_id': userId,
    'start_date': dateOnly(startDate),
    'end_date': endDate == null ? null : dateOnly(endDate!),
  };
}

/// [date] as `yyyy-mm-dd`, the form Postgres `date` columns take.
String dateOnly(DateTime date) =>
    '${date.year.toString().padLeft(4, '0')}-'
    '${date.month.toString().padLeft(2, '0')}-'
    '${date.day.toString().padLeft(2, '0')}';

/// [date] moved by [days] calendar days, at midnight.
DateTime addDays(DateTime date, int days) =>
    DateTime(date.year, date.month, date.day + days);

/// Calendar days from [from] to [to], whatever the clocks did in between.
int daysBetween(DateTime from, DateTime to) => DateTime.utc(
  to.year,
  to.month,
  to.day,
).difference(DateTime.utc(from.year, from.month, from.day)).inDays;

/// Every day of [periods]. A period with no end runs up to [today].
Set<DateTime> daysOfPeriods(Iterable<Period> periods, DateTime today) => {
  for (final period in periods)
    for (
      var day = period.startDate;
      !day.isAfter(period.endDate ?? today);
      day = addDays(day, 1)
    )
      day,
};

/// [days] as periods: each run of consecutive days becomes one, oldest first.
List<Period> periodsFromDays(Set<DateTime> days) {
  final sorted = days.toList()..sort();
  final periods = <Period>[];
  for (var i = 0; i < sorted.length; i++) {
    final start = sorted[i];
    while (i + 1 < sorted.length &&
        daysBetween(sorted[i], sorted[i + 1]) == 1) {
      i++;
    }
    periods.add(Period(startDate: start, endDate: sorted[i]));
  }
  return periods;
}
