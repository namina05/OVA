import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ova/app.dart';
import 'package:ova/auth/auth_providers.dart';
import 'package:ova/auth/auth_service.dart';
import 'package:ova/belt/belt_providers.dart';
import 'package:ova/belt/simulated_belt.dart';
import 'package:ova/chat/chat_providers.dart';
import 'package:ova/profile/profile_providers.dart';
import 'package:ova/sessions/session_providers.dart';
import 'package:ova/sessions/session_repository.dart';

import 'fake_auth_service.dart';
import 'fake_chat_service.dart';
import 'fake_profile_service.dart';

void main() {
  Future<void> pumpApp(WidgetTester tester, FakeAuthService auth) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.reset);

    final belt = SimulatedBelt(autoTick: false);
    addTearDown(belt.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authServiceProvider.overrideWithValue(auth),
          chatServiceProvider.overrideWithValue(FakeChatService()),
          profileServiceProvider.overrideWithValue(
            FakeProfileService(saved: ashaProfile),
          ),
          beltProvider.overrideWithValue(belt),
          sessionRepositoryProvider.overrideWithValue(
            SessionRepository(MemorySessionStore()),
          ),
        ],
        child: const MaterialApp(home: AuthGate()),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> fillIn(
    WidgetTester tester,
    String email,
    String password,
  ) async {
    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), email);
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Password'),
      password,
    );
  }

  testWidgets('signed out: sign in with the right password, then sign out', (
    tester,
  ) async {
    final auth = FakeAuthService()
      ..passwords['asha@example.com'] = 'correct-horse';
    await pumpApp(tester, auth);
    expect(find.text('Sign in to continue'), findsOneWidget);
    expect(find.text('Therapy'), findsNothing);

    await fillIn(tester, 'asha@example.com', 'wrong-password');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Wrong email or password.'), findsOneWidget);
    expect(auth.currentUser, isNull);

    await fillIn(tester, ' asha@example.com ', 'correct-horse');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('asha@example.com'), findsOneWidget);
    expect(find.text('Therapy'), findsOneWidget);

    await tester.tap(find.text('Asha'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(find.text('Sign in to continue'), findsOneWidget);
    expect(auth.currentUser, isNull);
  });

  testWidgets('already signed in: opens straight into the app', (tester) async {
    await pumpApp(
      tester,
      FakeAuthService(
        signedInAs: const AppUser(id: 'id-asha', email: 'asha@example.com'),
      ),
    );
    expect(find.text('asha@example.com'), findsOneWidget);
    expect(find.text('Sign in to continue'), findsNothing);
  });

  testWidgets('creating an account signs the user in', (tester) async {
    final auth = FakeAuthService();
    await pumpApp(tester, auth);
    await tester.tap(find.text('Create a new account'));
    await tester.pumpAndSettle();
    expect(find.text('Create your account'), findsOneWidget);

    await fillIn(tester, 'new@example.com', 'long-enough-pw');
    await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
    await tester.pumpAndSettle();
    expect(find.text('new@example.com'), findsOneWidget);
  });

  testWidgets(
    'when email confirmation is required, the user is told to check email',
    (tester) async {
      final auth = FakeAuthService(requireEmailConfirmation: true);
      await pumpApp(tester, auth);
      await tester.tap(find.text('Create a new account'));
      await tester.pumpAndSettle();
      await fillIn(tester, 'new@example.com', 'long-enough-pw');
      await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('Open the link we emailed to new@example.com'),
        findsOneWidget,
      );
      expect(find.text('Sign in to continue'), findsOneWidget);
      expect(auth.currentUser, isNull);
    },
  );

  testWidgets(
    'rejects a bad email and a short new password before calling the server',
    (tester) async {
      final auth = FakeAuthService();
      await pumpApp(tester, auth);
      await tester.tap(find.text('Create a new account'));
      await tester.pumpAndSettle();
      await fillIn(tester, 'not-an-email', 'short');
      await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
      await tester.pumpAndSettle();

      expect(find.text('Enter a valid email address'), findsOneWidget);
      expect(find.text('Use at least 8 characters'), findsOneWidget);
      expect(auth.passwords, isEmpty);
    },
  );

  testWidgets('creating an account that already exists shows the reason', (
    tester,
  ) async {
    final auth = FakeAuthService()
      ..passwords['asha@example.com'] = 'correct-horse';
    await pumpApp(tester, auth);
    await tester.tap(find.text('Create a new account'));
    await tester.pumpAndSettle();
    await fillIn(tester, 'asha@example.com', 'another-password');
    await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
    await tester.pumpAndSettle();

    expect(
      find.text('An account with this email already exists.'),
      findsOneWidget,
    );
  });
}
