/// Limits the `profiles` table enforces, so forms can reject a value before
/// it is sent.
const maxNameLength = 50;
const minCycleLength = 15;
const maxCycleLength = 60;
const minPeriodLength = 1;
const maxPeriodLength = 15;

/// What the user told the app about themselves: one row of `profiles`.
class Profile {
  const Profile({
    required this.displayName,
    required this.dateOfBirth,
    required this.consentAt,
    this.typicalCycleLength,
    this.typicalPeriodLength,
    this.chatbotDataAccess = true,
  });

  factory Profile.fromRow(Map<String, dynamic> row) => Profile(
    displayName: row['display_name'] as String,
    dateOfBirth: DateTime.parse(row['date_of_birth'] as String),
    consentAt: DateTime.parse(row['consent_at'] as String),
    typicalCycleLength: row['typical_cycle_length'] as int?,
    typicalPeriodLength: row['typical_period_length'] as int?,
    chatbotDataAccess: row['chatbot_data_access'] as bool,
  );

  final String displayName;

  /// A calendar date; the time of day is not used.
  final DateTime dateOfBirth;

  /// When the user agreed to their health data being stored.
  final DateTime consentAt;

  /// In days. Null until the user says, or the app has learned it.
  final int? typicalCycleLength;
  final int? typicalPeriodLength;

  /// Whether the assistant may read the user's sessions and cycle logs
  /// (SRS FR-DAT-3).
  final bool chatbotDataAccess;

  Map<String, dynamic> toRow({required String userId}) => {
    'id': userId,
    'display_name': displayName,
    'date_of_birth': _dateOnly(dateOfBirth),
    'consent_at': consentAt.toUtc().toIso8601String(),
    'typical_cycle_length': typicalCycleLength,
    'typical_period_length': typicalPeriodLength,
    'chatbot_data_access': chatbotDataAccess,
  };

  static String _dateOnly(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';
}
