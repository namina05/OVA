import 'package:ova/cycle/cycle_prediction.dart';
import 'package:ova/cycle/cycle_service.dart';
import 'package:ova/cycle/period.dart';
import 'package:ova/cycle/prediction_service.dart';

/// An in-memory period store for tests.
class FakeCycleService implements CycleService {
  FakeCycleService({List<Period>? saved}) : saved = saved ?? [];

  final List<Period> saved;
  int _nextId = 1;

  /// When true every call fails, as it would with no internet.
  bool offline = false;

  @override
  Future<List<Period>> periods() async {
    _checkOnline();
    return List.of(saved)..sort((a, b) => b.startDate.compareTo(a.startDate));
  }

  @override
  Future<void> save(Period period) async {
    _checkOnline();
    if (saved.any(
      (other) => other.id != period.id && other.startDate == period.startDate,
    )) {
      throw const CycleFailure(
        'You have already logged a period starting that day.',
      );
    }
    saved.removeWhere((other) => other.id == period.id);
    saved.add(
      Period(
        id: period.id ?? 'period-${_nextId++}',
        startDate: period.startDate,
        endDate: period.endDate,
      ),
    );
  }

  @override
  Future<void> delete(String id) async {
    _checkOnline();
    saved.removeWhere((period) => period.id == id);
  }

  void _checkOnline() {
    if (offline) throw const CycleFailure('Could not reach the server.');
  }
}

/// A backend that always forecasts [prediction].
class FakePredictionService implements PredictionService {
  FakePredictionService({this.prediction});

  CyclePrediction? prediction;

  /// When true the backend cannot be reached.
  bool offline = false;
  int asked = 0;

  @override
  Future<CyclePrediction?> predict() async {
    asked++;
    if (offline) {
      throw const CycleFailure('Could not reach the prediction service.');
    }
    return prediction;
  }
}
