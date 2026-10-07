import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_providers.dart';
import '../profile/profile.dart';
import '../profile/profile_providers.dart';
import 'profile_form.dart';

/// The user's profile, which they can edit here, and the way to sign out.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  Future<void> _save(
    BuildContext context,
    WidgetRef ref,
    Profile profile,
  ) async {
    await ref.read(profileProvider.notifier).save(profile);
    if (!context.mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('Profile saved')));
  }

  void _signOut(BuildContext context, WidgetRef ref) {
    // Back to the first screen, which becomes the sign-in screen.
    Navigator.of(context).popUntil((route) => route.isFirst);
    ref.read(authServiceProvider).signOut();
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final user = ref.watch(currentUserProvider).valueOrNull;
    final profile = ref.watch(profileProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (user != null) ...[
            Text('Email', style: theme.textTheme.labelMedium),
            Text(user.email, style: theme.textTheme.bodyLarge),
            const SizedBox(height: 24),
          ],
          profile.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (_, _) => Column(
              children: [
                const Text('Could not load your profile.'),
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: () => ref.invalidate(profileProvider),
                  child: const Text('Try again'),
                ),
              ],
            ),
            data: (profile) => profile == null
                ? const SizedBox.shrink()
                : ProfileForm(
                    initial: profile,
                    submitLabel: 'Save changes',
                    onSubmit: (edited) => _save(context, ref, edited),
                  ),
          ),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: () => _signOut(context, ref),
            icon: const Icon(Icons.logout),
            label: const Text('Sign out'),
          ),
        ],
      ),
    );
  }
}
