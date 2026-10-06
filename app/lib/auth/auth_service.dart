import 'package:supabase_flutter/supabase_flutter.dart';

class AppUser {
  const AppUser({required this.id, required this.email});

  final String id;
  final String email;

  @override
  bool operator ==(Object other) =>
      other is AppUser && other.id == id && other.email == email;

  @override
  int get hashCode => Object.hash(id, email);
}

/// A sign-in or sign-up problem, with a message fit to show the user.
class AuthFailure implements Exception {
  const AuthFailure(this.message);
  final String message;

  @override
  String toString() => 'AuthFailure: $message';
}

/// The app's only view of accounts, so screens and tests do not depend on
/// Supabase directly.
abstract interface class AuthService {
  AppUser? get currentUser;

  /// Emits the signed-in user, or null when signed out. Emits the current
  /// state as soon as it is listened to.
  Stream<AppUser?> get userChanges;

  Future<void> signIn({required String email, required String password});

  /// Returns true when the new account must be confirmed by email before it
  /// can sign in.
  Future<bool> signUp({required String email, required String password});

  Future<void> signOut();
}

class SupabaseAuthService implements AuthService {
  SupabaseAuthService(this._auth);

  final GoTrueClient _auth;

  @override
  AppUser? get currentUser => _toUser(_auth.currentUser);

  @override
  Stream<AppUser?> get userChanges =>
      _auth.onAuthStateChange.map((state) => _toUser(state.session?.user));

  @override
  Future<void> signIn({required String email, required String password}) =>
      _guard(() => _auth.signInWithPassword(email: email, password: password));

  @override
  Future<bool> signUp({required String email, required String password}) async {
    final response = await _guard(
      () => _auth.signUp(email: email, password: password),
    );
    return response.session == null;
  }

  // Local scope: signing out must work with no internet.
  @override
  Future<void> signOut() =>
      _guard(() => _auth.signOut(scope: SignOutScope.local));

  static AppUser? _toUser(User? user) =>
      user == null ? null : AppUser(id: user.id, email: user.email ?? '');

  static Future<T> _guard<T>(Future<T> Function() action) async {
    try {
      return await action();
    } on AuthRetryableFetchException {
      throw const AuthFailure(
        'Could not reach the server. Check your internet connection.',
      );
    } on AuthException catch (e) {
      throw AuthFailure(switch (e.code) {
        'invalid_credentials' => 'Wrong email or password.',
        'email_not_confirmed' =>
          'Confirm your email first, using the link we sent you.',
        'user_already_exists' ||
        'email_exists' => 'An account with this email already exists.',
        'weak_password' => 'Choose a stronger password.',
        'over_email_send_rate_limit' =>
          'Too many attempts. Wait a few minutes and try again.',
        _ => e.message,
      });
    }
  }
}
