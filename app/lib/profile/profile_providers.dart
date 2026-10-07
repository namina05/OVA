import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../auth/auth_providers.dart';
import 'profile.dart';
import 'profile_service.dart';

final profileServiceProvider = Provider<ProfileService>((ref) {
  final userId = ref.watch(
    currentUserProvider.select((user) => user.valueOrNull?.id),
  );
  if (userId == null) throw StateError('No one is signed in');
  return SupabaseProfileService(Supabase.instance.client, userId: userId);
});

/// The signed-in user's profile: null when they have not set one up, and an
/// error when it could not be fetched.
final profileProvider = AsyncNotifierProvider<ProfileController, Profile?>(
  ProfileController.new,
);

class ProfileController extends AsyncNotifier<Profile?> {
  @override
  Future<Profile?> build() {
    // Watching the user id reloads the profile when the account changes.
    final userId = ref.watch(
      currentUserProvider.select((user) => user.valueOrNull?.id),
    );
    if (userId == null) return Future.value();
    return ref.watch(profileServiceProvider).load();
  }

  /// Stores [profile] and shows it across the app. Throws [ProfileFailure]
  /// if it could not be stored.
  Future<void> save(Profile profile) async {
    await ref.read(profileServiceProvider).save(profile);
    state = AsyncData(profile);
  }
}
