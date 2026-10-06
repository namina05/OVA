import 'dart:async';

import 'package:ova/auth/auth_service.dart';

/// In-memory accounts for tests.
class FakeAuthService implements AuthService {
  FakeAuthService({AppUser? signedInAs, this.requireEmailConfirmation = false})
    : _user = signedInAs;

  final bool requireEmailConfirmation;
  final Map<String, String> passwords = {};
  final _changes = StreamController<AppUser?>.broadcast();
  AppUser? _user;

  @override
  AppUser? get currentUser => _user;

  @override
  Stream<AppUser?> get userChanges async* {
    yield _user;
    yield* _changes.stream;
  }

  @override
  Future<void> signIn({required String email, required String password}) async {
    if (passwords[email] != password) {
      throw const AuthFailure('Wrong email or password.');
    }
    _set(AppUser(id: 'id-$email', email: email));
  }

  @override
  Future<bool> signUp({required String email, required String password}) async {
    if (passwords.containsKey(email)) {
      throw const AuthFailure('An account with this email already exists.');
    }
    passwords[email] = password;
    if (requireEmailConfirmation) return true;
    _set(AppUser(id: 'id-$email', email: email));
    return false;
  }

  @override
  Future<void> signOut() async => _set(null);

  void _set(AppUser? user) {
    _user = user;
    _changes.add(user);
  }
}
