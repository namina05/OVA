import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ova/cycle/cycle_prediction.dart';
import 'package:ova/cycle/cycle_providers.dart';
import 'package:ova/cycle/period.dart';
import 'package:ova/screens/cycle_screen.dart';

import 'fake_cycle_service.dart';

void main() {
  late FakeCycleService cycle;
  late FakePredictionService predictions;

  final today = DateUtils.dateOnly(DateTime.now());

  Future<void> pumpScreen(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          cycleServiceProvider.overrideWithValue(cycle),
          predictionServiceProvider.overrideWithValue(predictions),
        ],
        child: const MaterialApp(home: CycleScreen()),
      ),
    );
    await tester.pumpAndSettle();
  }

  setUp(() {
    cycle = FakeCycleService();
    predictions = FakePredictionService(
      prediction: CyclePrediction(
        predictedStart: today.add(const Duration(days: 12)),
        rangeDays: 3,
        predictedPeriodLength: 5,
        daysUntilStart: 12,
        isLate: false,
        explanation: 'Based on your last 3 cycles.',
        notice: 'Predictions are estimates.',
      ),
    );
  });

  testWidgets('with no periods it invites the first log and predicts nothing', (
    tester,
  ) async {
    await pumpScreen(tester);
    expect(find.text('No periods logged yet'), findsOneWidget);
    expect(find.textContaining('Log the first day'), findsOneWidget);
    expect(predictions.asked, 0);
  });

  Finder day(DateTime date) => find.byKey(ValueKey('day-${dateOnly(date)}'));

  Future<void> openCalendar(WidgetTester tester, String button) async {
    await tester.tap(find.text(button));
    await tester.pumpAndSettle();
  }

  Future<void> save(WidgetTester tester) async {
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
  }

  testWidgets('tapping today logs a period and shows the prediction', (
    tester,
  ) async {
    await pumpScreen(tester);
    await openCalendar(tester, 'Log period');
    await tester.tap(day(today));
    await tester.pumpAndSettle();
    await save(tester);

    expect(cycle.saved.single.startDate, today);
    expect(cycle.saved.single.endDate, today);
    expect(find.text('1 day'), findsOneWidget);
    expect(find.text('In 12 days'), findsOneWidget);
    expect(find.text('Edit period dates'), findsOneWidget);
  });

  testWidgets('a past day on its own marks a usual-length period', (
    tester,
  ) async {
    final start = addDays(today, -40);
    await pumpScreen(tester);
    await openCalendar(tester, 'Log period');
    await tester.scrollUntilVisible(
      day(start),
      200,
      scrollable: find.byType(Scrollable),
    );
    await tester.ensureVisible(day(start));
    await tester.pumpAndSettle();
    await tester.tap(day(start));
    await tester.pumpAndSettle();
    await save(tester);

    expect(cycle.saved.single.startDate, start);
    expect(cycle.saved.single.endDate, addDays(start, 4));
  });

  testWidgets('tapping days extends and shortens a logged period', (
    tester,
  ) async {
    cycle = FakeCycleService(
      saved: [
        Period(
          id: 'p1',
          startDate: addDays(today, -3),
          endDate: addDays(today, -2),
        ),
      ],
    );
    await pumpScreen(tester);
    await openCalendar(tester, 'Edit period dates');
    await tester.ensureVisible(day(addDays(today, -3)));
    await tester.tap(day(addDays(today, -1)));
    await tester.pumpAndSettle();
    await save(tester);
    expect(cycle.saved.single.id, 'p1');
    expect(cycle.saved.single.endDate, addDays(today, -1));

    await openCalendar(tester, 'Edit period dates');
    await tester.tap(day(addDays(today, -1)));
    await tester.tap(day(addDays(today, -2)));
    await tester.pumpAndSettle();
    await save(tester);
    expect(cycle.saved.single.endDate, addDays(today, -3));
  });

  testWidgets('unmarking every day of a period deletes it', (tester) async {
    cycle = FakeCycleService(
      saved: [Period(id: 'p1', startDate: today, endDate: today)],
    );
    await pumpScreen(tester);
    await openCalendar(tester, 'Edit period dates');
    await tester.tap(day(today));
    await tester.pumpAndSettle();
    await save(tester);

    expect(cycle.saved, isEmpty);
    expect(find.text('No periods logged yet'), findsOneWidget);
  });

  testWidgets('a future day cannot be marked', (tester) async {
    await pumpScreen(tester);
    await openCalendar(tester, 'Log period');
    final tomorrow = day(addDays(today, 1));
    if (tomorrow.evaluate().isNotEmpty) {
      await tester.tap(tomorrow);
      await tester.pumpAndSettle();
    }
    await save(tester);

    expect(cycle.saved, isEmpty);
  });

  testWidgets('periods still show when the backend cannot be reached', (
    tester,
  ) async {
    cycle = FakeCycleService(
      saved: [Period(id: 'p1', startDate: today)],
    );
    predictions.offline = true;
    await pumpScreen(tester);

    expect(find.text('Ongoing'), findsOneWidget);
    expect(
      find.text('Could not reach the prediction service.'),
      findsOneWidget,
    );
  });
}
