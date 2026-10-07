import 'package:supabase_flutter/supabase_flutter.dart';

import 'profile.dart';

/// A problem reading or saving the profile, with a message fit to show the
/// user.
class ProfileFailure implements Exception {
  const ProfileFailure(this.message);
  final String message;

  @override
  String toString() => 'ProfileFailure: $message';
}

/// The app's only view of the stored profile, so screens and tests do not
/// depend on Supabase directly.
abstract interface class ProfileService {
  /// The signed-in user's profile, or null if they have not set one up.
  Future<Profile?> load();

  /// Creates the profile, or replaces it if there is one.
  Future<void> save(Profile profile);
}

/// Keeps one account's profile in the Supabase `profiles` table. Row-level
/// security limits every call to the signed-in user's own row.
class SupabaseProfileService implements ProfileService {
  SupabaseProfileService(this._client, {required this.userId});

  final SupabaseClient _client;
  final String userId;

  @override
  Future<Profile?> load() => _guard(() async {
    final row = await _client
        .from('profiles')
        .select()
        .eq('id', userId)
        .maybeSingle();
    return row == null ? null : Profile.fromRow(row);
  });

  @override
  Future<void> save(Profile profile) => _guard(
    () => _client.from('profiles').upsert(profile.toRow(userId: userId)),
  );

  static Future<T> _guard<T>(Future<T> Function() action) async {
    try {
      return await action();
    } on PostgrestException {
      throw const ProfileFailure(
        'Something went wrong. Try again in a moment.',
      );
    } catch (_) {
      throw const ProfileFailure(
        'Could not reach the server. Check your internet connection.',
      );
    }
  }
}
