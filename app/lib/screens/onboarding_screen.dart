import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_providers.dart';
import '../profile/profile_providers.dart';
import 'profile_form.dart';

/// Shown once after an account is created: the app needs a profile, and the
/// user's consent, before it stores anything about them.
class OnboardingScreen extends ConsumerWidget {
  const OnboardingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Set up your profile', style: theme.textTheme.headlineSmall),
              const SizedBox(height: 8),
              const Text('You can change these details later.'),
              const SizedBox(height: 24),
              ProfileForm(
                submitLabel: 'Continue',
                onSubmit: ref.read(profileProvider.notifier).save,
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => ref.read(authServiceProvider).signOut(),
                child: const Text('Sign out'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
