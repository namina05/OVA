import 'package:ova/profile/profile.dart';
import 'package:ova/profile/profile_service.dart';

/// A profile every test account can start with.
final ashaProfile = Profile(
  displayName: 'Asha',
  dateOfBirth: DateTime(2001, 5, 17),
  consentAt: DateTime.utc(2026, 10, 1),
);

/// An in-memory profile store for tests.
class FakeProfileService implements ProfileService {
  FakeProfileService({this.saved});

  Profile? saved;

  /// When true every call fails, as it would with no internet.
  bool offline = false;

  @override
  Future<Profile?> load() async {
    _checkOnline();
    return saved;
  }

  @override
  Future<void> save(Profile profile) async {
    _checkOnline();
    saved = profile;
  }

  void _checkOnline() {
    if (offline) throw const ProfileFailure('Could not reach the server.');
  }
}
