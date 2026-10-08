import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ova/auth/auth_providers.dart';
import 'package:ova/auth/auth_service.dart';
import 'package:ova/cycle/cycle_prediction.dart';
import 'package:ova/cycle/cycle_providers.dart';
import 'package:ova/cycle/period.dart';
import 'package:ova/profile/profile_providers.dart';
import 'package:ova/screens/home_screen.dart';

import 'fake_auth_service.dart';
import 'fake_cycle_service.dart';
import 'fake_profile_service.dart';

void main() {
  final today = DateUtils.dateOnly(DateTime.now());

  testWidgets('home shows the prediction and logs a period from its calendar', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.reset);

    final cycle = FakeCycleService();
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
          profileServiceProvider.overrideWithValue(
            FakeProfileService(saved: ashaProfile),
          ),
          cycleServiceProvider.overrideWithValue(cycle),
          predictionServiceProvider.overrideWithValue(
            FakePredictionService(
              prediction: CyclePrediction(
                predictedStart: addDays(today, 28),
                rangeDays: 3,
                predictedPeriodLength: 5,
                ovulationDate: addDays(today, 14),
                fertileStart: addDays(today, 9),
                fertileEnd: addDays(today, 15),
                daysUntilStart: 28,
                isLate: false,
                explanation: 'Based on a 28-day cycle.',
                notice: 'Predictions are estimates.',
              ),
            ),
          ),
        ],
        child: const MaterialApp(home: HomeScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Next period'), findsOneWidget);
    expect(find.textContaining('Log the first day'), findsOneWidget);

    // Tapping a day on the home calendar opens the calendar to mark days.
    final todayCell = find.byKey(ValueKey('day-${dateOnly(today)}'));
    await tester.tap(todayCell);
    await tester.pumpAndSettle();
    expect(find.text('Save'), findsOneWidget);
    expect(cycle.saved, isEmpty);

    await tester.tap(todayCell.last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(cycle.saved.single.startDate, today);
    expect(find.text('In 28 days'), findsOneWidget);
    expect(find.textContaining('Estimated ovulation: '), findsOneWidget);
    expect(find.text('Fertile'), findsOneWidget);
    expect(find.text('Edit period dates'), findsOneWidget);
  });
}
