import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../auth/auth_providers.dart';
import '../backend_config.dart';
import 'cycle_prediction.dart';
import 'cycle_service.dart';
import 'period.dart';
import 'prediction_service.dart';

final cycleServiceProvider = Provider<CycleService>((ref) {
  final userId = ref.watch(
    currentUserProvider.select((user) => user.valueOrNull?.id),
  );
  if (userId == null) throw StateError('No one is signed in');
  return SupabaseCycleService(Supabase.instance.client, userId: userId);
});

final predictionServiceProvider = Provider<PredictionService>((ref) {
  final userId = ref.watch(
    currentUserProvider.select((user) => user.valueOrNull?.id),
  );
  if (userId == null) throw StateError('No one is signed in');
  return BackendPredictionService(
    baseUrl: backendUrl,
    userId: userId,
    accessToken: () =>
        Supabase.instance.client.auth.currentSession?.accessToken,
  );
});

/// The signed-in user's logged periods, newest first.
final periodsProvider = AsyncNotifierProvider<PeriodsController, List<Period>>(
  PeriodsController.new,
);

class PeriodsController extends AsyncNotifier<List<Period>> {
  @override
  Future<List<Period>> build() => ref.watch(cycleServiceProvider).periods();

  /// Makes the stored periods match [days], the days the user marked on the
  /// calendar. Throws [CycleFailure] if a change could not be stored.
  Future<void> setDays(Set<DateTime> days) async {
    final service = ref.read(cycleServiceProvider);
    final stored = {
      for (final period in await future) period.startDate: period,
    };
    final wanted = periodsFromDays(days);
    try {
      for (final period in stored.values) {
        if (!wanted.any((other) => other.startDate == period.startDate)) {
          await service.delete(period.id!);
        }
      }
      for (final period in wanted) {
        final existing = stored[period.startDate];
        if (existing == null) {
          await service.save(period);
        } else if (existing.endDate != period.endDate) {
          await service.save(
            Period(
              id: existing.id,
              startDate: period.startDate,
              endDate: period.endDate,
            ),
          );
        }
      }
    } finally {
      // Whatever was stored before a failure still shows.
      await _reload();
    }
  }

  Future<void> _reload() async {
    state = await AsyncValue.guard(ref.read(cycleServiceProvider).periods);
  }
}

/// The forecast of the next period, asked for again whenever the logged
/// periods change. Null when there is nothing to predict from yet.
final cyclePredictionProvider = FutureProvider<CyclePrediction?>((ref) async {
  final periods = await ref.watch(periodsProvider.future);
  if (periods.isEmpty) return null;
  return ref.watch(predictionServiceProvider).predict();
});
