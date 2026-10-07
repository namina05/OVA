import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ova/app.dart';
import 'package:ova/auth/auth_providers.dart';
import 'package:ova/auth/auth_service.dart';
import 'package:ova/belt/belt_models.dart';
import 'package:ova/belt/belt_providers.dart';
import 'package:ova/belt/simulated_belt.dart';
import 'package:ova/chat/chat_providers.dart';
import 'package:ova/profile/profile_providers.dart';
import 'package:ova/sessions/session_providers.dart';
import 'package:ova/sessions/session_record.dart';
import 'package:ova/sessions/session_repository.dart';

import 'fake_auth_service.dart';
import 'fake_chat_service.dart';
import 'fake_profile_service.dart';

void main() {
  late SimulatedBelt belt;
  late MemorySessionStore store;

  Future<SessionRepository> pumpApp(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.reset);

    final repository = SessionRepository(store);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authServiceProvider.overrideWithValue(
            FakeAuthService(
              signedInAs: const AppUser(
                id: 'id-asha',
                email: 'asha@example.com',
              ),
            ),
          ),
          beltProvider.overrideWithValue(belt),
          chatServiceProvider.overrideWithValue(FakeChatService()),
          profileServiceProvider.overrideWithValue(
            FakeProfileService(saved: ashaProfile),
          ),
          sessionRepositoryProvider.overrideWithValue(repository),
        ],
        child: const MaterialApp(home: HomeShell()),
      ),
    );
    await tester.pumpAndSettle();
    return repository;
  }

  Future<void> runShortSession(WidgetTester tester) async {
    await belt.setZoneLevels([
      HeatLevel.high,
      HeatLevel.off,
      HeatLevel.off,
      HeatLevel.off,
    ]);
    await belt.start(const Duration(seconds: 3));
    for (var i = 0; i < 3; i++) {
      belt.tick();
      await tester.pump();
    }
    await tester.pumpAndSettle();
  }

  setUp(() {
    belt = SimulatedBelt(autoTick: false);
    store = MemorySessionStore();
  });

  tearDown(() => belt.dispose());

  testWidgets(
    'rating a finished session saves the score and shows it in History',
    (tester) async {
      final repository = await pumpApp(tester);
      await runShortSession(tester);

      expect(find.text('How much relief did you get?'), findsOneWidget);
      await tester.tap(find.widgetWithText(ChoiceChip, '4'));
      await tester.pump();
      await tester.enterText(find.byType(TextField), 'Lower cramps eased');
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();

      final session = (await tester.runAsync(repository.all))!.single;
      expect(session.reliefScore, 4);
      expect(session.note, 'Lower cramps eased');
      expect(session.endReason, EndReason.completed);

      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();
      expect(find.text('4/5'), findsOneWidget);
      expect(find.textContaining('Upper left High'), findsOneWidget);

      await tester.tap(find.text('4/5'));
      await tester.pumpAndSettle();
      expect(find.text('Relief: 4/5 (Good)'), findsOneWidget);
      expect(find.text('Lower cramps eased'), findsOneWidget);
    },
  );

  testWidgets(
    'a skipped rating is asked for once more on the next launch, then dropped',
    (tester) async {
      var repository = await pumpApp(tester);
      await runShortSession(tester);
      await tester.tap(find.text('Skip'));
      await tester.pumpAndSettle();
      expect((await tester.runAsync(repository.all))!.single.reliefPrompts, 1);

      // Second launch: asked again, skipped again.
      await tester.pumpWidget(const SizedBox());
      repository = await pumpApp(tester);
      expect(find.text('How much relief did you get?'), findsOneWidget);
      await tester.tap(find.text('Skip'));
      await tester.pumpAndSettle();
      final session = (await tester.runAsync(repository.all))!.single;
      expect(session.reliefPrompts, 2);
      expect(session.reliefScore, isNull);

      // Third launch: not asked.
      await tester.pumpWidget(const SizedBox());
      await pumpApp(tester);
      expect(find.text('How much relief did you get?'), findsNothing);

      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();
      expect(find.text('Not rated'), findsOneWidget);
    },
  );

  testWidgets(
    'an unrated session can be rated or deleted from its detail page',
    (tester) async {
      final repository = await pumpApp(tester);
      await runShortSession(tester);
      await tester.tap(find.text('Skip'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('History'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Not rated'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Rate this session'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ChoiceChip, '2'));
      await tester.pump();
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();
      expect(find.text('2/5'), findsOneWidget);

      await tester.tap(find.text('2/5'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Delete session'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      expect(find.text('No sessions yet'), findsOneWidget);
      expect(await tester.runAsync(repository.all), isEmpty);
    },
  );
}
