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
  late FakeAuthService auth;
  late FakeProfileService profiles;

  Future<void> pumpApp(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.reset);

    final belt = SimulatedBelt(autoTick: false);
    addTearDown(belt.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authServiceProvider.overrideWithValue(auth),
          profileServiceProvider.overrideWithValue(profiles),
          chatServiceProvider.overrideWithValue(FakeChatService()),
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

  /// Opens the date picker and accepts the date it starts on.
  Future<void> pickDateOfBirth(WidgetTester tester) async {
    await tester.tap(find.widgetWithText(TextFormField, 'Date of birth'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
  }

  setUp(() {
    auth = FakeAuthService(
      signedInAs: const AppUser(id: 'id-asha', email: 'asha@example.com'),
    );
    profiles = FakeProfileService(saved: ashaProfile);
  });

  testWidgets('a new user sets up a profile before reaching the app', (
    tester,
  ) async {
    profiles = FakeProfileService();
    await pumpApp(tester);
    expect(find.text('Set up your profile'), findsOneWidget);
    expect(find.text('Therapy'), findsNothing);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Name'),
      ' Asha ',
    );
    await pickDateOfBirth(tester);
    await tester.enterText(
      find.widgetWithText(
        TextFormField,
        'Typical cycle length in days (optional)',
      ),
      '29',
    );
    await tester.tap(find.byType(Checkbox));
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    expect(find.text('Therapy'), findsOneWidget);
    expect(find.text('Asha'), findsOneWidget);
    final saved = profiles.saved!;
    expect(saved.displayName, 'Asha');
    expect(saved.dateOfBirth, DateTime(DateTime.now().year - 20));
    expect(saved.typicalCycleLength, 29);
    expect(saved.typicalPeriodLength, isNull);
    expect(saved.chatbotDataAccess, isTrue);
  });

  testWidgets('setup needs a name, a date of birth and consent', (
    tester,
  ) async {
    profiles = FakeProfileService();
    await pumpApp(tester);

    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Enter your name'), findsOneWidget);
    expect(find.text('Choose your date of birth'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Asha');
    await pickDateOfBirth(tester);
    await tester.enterText(
      find.widgetWithText(
        TextFormField,
        'Typical cycle length in days (optional)',
      ),
      '90',
    );
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Enter 15 to 60 days, or leave empty'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(
        TextFormField,
        'Typical cycle length in days (optional)',
      ),
      '',
    );
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(
      find.text('Tick the box to agree before continuing.'),
      findsOneWidget,
    );
    expect(profiles.saved, isNull);
  });

  testWidgets('the home tile opens the profile, where it can be edited', (
    tester,
  ) async {
    await pumpApp(tester);
    await tester.tap(find.text('Asha'));
    await tester.pumpAndSettle();
    expect(find.text('asha@example.com'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Name'),
      'Asha Rao',
    );
    await tester.enterText(
      find.widgetWithText(
        TextFormField,
        'Typical period length in days (optional)',
      ),
      '5',
    );
    await tester.tap(find.byType(Switch));
    await tester.tap(find.text('Save changes'));
    await tester.pumpAndSettle();

    expect(find.text('Profile saved'), findsOneWidget);
    final saved = profiles.saved!;
    expect(saved.displayName, 'Asha Rao');
    expect(saved.typicalPeriodLength, 5);
    expect(saved.chatbotDataAccess, isFalse);
    expect(saved.dateOfBirth, ashaProfile.dateOfBirth);
    expect(saved.consentAt, ashaProfile.consentAt);

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Asha Rao'), findsOneWidget);
  });

  testWidgets('a change that cannot be saved says so and is not kept', (
    tester,
  ) async {
    await pumpApp(tester);
    await tester.tap(find.text('Asha'));
    await tester.pumpAndSettle();
    profiles.offline = true;

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Name'),
      'Asha Rao',
    );
    await tester.tap(find.text('Save changes'));
    await tester.pumpAndSettle();

    expect(find.text('Could not reach the server.'), findsOneWidget);
    expect(profiles.saved!.displayName, 'Asha');
  });

  testWidgets(
    'with no internet the app still opens, without asking for setup',
    (tester) async {
      profiles.offline = true;
      await pumpApp(tester);

      expect(find.text('Set up your profile'), findsNothing);
      expect(find.text('Therapy'), findsOneWidget);
      expect(find.text('asha@example.com'), findsOneWidget);
    },
  );
}
