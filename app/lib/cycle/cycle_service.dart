import 'package:supabase_flutter/supabase_flutter.dart';

import 'period.dart';

/// A problem reading or saving cycle data, with a message fit to show the
/// user.
class CycleFailure implements Exception {
  const CycleFailure(this.message);
  final String message;

  @override
  String toString() => 'CycleFailure: $message';
}

/// The app's only view of the stored periods, so screens and tests do not
/// depend on Supabase directly.
abstract interface class CycleService {
  /// The user's logged periods, newest first.
  Future<List<Period>> periods();

  /// Stores [period], replacing the stored one when it has an id.
  Future<void> save(Period period);

  Future<void> delete(String id);
}

/// Keeps one account's periods in the Supabase `periods` table. Row-level
/// security limits every call to the signed-in user's own rows.
class SupabaseCycleService implements CycleService {
  SupabaseCycleService(this._client, {required this.userId});

  /// Postgres' code for breaking a unique constraint.
  static const _uniqueViolation = '23505';

  final SupabaseClient _client;
  final String userId;

  @override
  Future<List<Period>> periods() => _guard(() async {
    final rows = await _client
        .from('periods')
        .select('id, start_date, end_date')
        .order('start_date', ascending: false);
    return [for (final row in rows) Period.fromRow(row)];
  });

  @override
  Future<void> save(Period period) => _guard(() async {
    final row = period.toRow(userId: userId);
    final id = period.id;
    if (id == null) {
      await _client.from('periods').insert(row);
    } else {
      await _client.from('periods').update(row).eq('id', id);
    }
  });

  @override
  Future<void> delete(String id) =>
      _guard(() => _client.from('periods').delete().eq('id', id));

  static Future<T> _guard<T>(Future<T> Function() action) async {
    try {
      return await action();
    } on PostgrestException catch (error) {
      throw CycleFailure(
        error.code == _uniqueViolation
            ? 'You have already logged a period starting that day.'
            : 'Something went wrong. Try again in a moment.',
      );
    } catch (_) {
      throw const CycleFailure(
        'Could not reach the server. Check your internet connection.',
      );
    }
  }
}
