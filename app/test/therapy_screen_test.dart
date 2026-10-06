import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ova/belt/belt_models.dart';
import 'package:ova/belt/belt_providers.dart';
import 'package:ova/belt/simulated_belt.dart';
import 'package:ova/screens/therapy_screen.dart';

void main() {
  testWidgets('start is disabled until a zone is on, then runs and stops',
      (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.reset);

    final belt = SimulatedBelt(autoTick: false);
    addTearDown(belt.dispose);
    BeltTelemetry? last;
    belt.telemetry.listen((frame) => last = frame);

    await tester.pumpWidget(ProviderScope(
      overrides: [beltProvider.overrideWithValue(belt)],
      child: const MaterialApp(home: TherapyScreen()),
    ));
    await tester.pump();

    FilledButton startButton() => tester.widget<FilledButton>(
        find.ancestor(of: find.text('Start session'), matching: find.bySubtype<FilledButton>()));
    expect(startButton().onPressed, isNull);

    await tester.tap(find.text('High').first);
    await tester.pump();
    expect(startButton().onPressed, isNotNull);

    await tester.tap(find.text('Start session'));
    await tester.pump();
    belt.tick();
    await tester.pump();
    await tester.pump();

    expect(last!.state, SessionState.running);
    expect(last!.zoneLevels.first, HeatLevel.high);
    expect(find.text('19:59'), findsOneWidget);
    expect(find.text('Stop'), findsOneWidget);

    await tester.tap(find.text('Stop'));
    await tester.pump();
    await tester.pump();

    expect(last!.state, SessionState.idle);
    expect(find.text('Start session'), findsOneWidget);
  });
}
