import 'dart:convert';

import 'package:http/http.dart' as http;

import 'cycle_prediction.dart';
import 'cycle_service.dart';

/// The app's only view of the backend's cycle model, so screens and tests do
/// not depend on the network.
abstract interface class PredictionService {
  /// The forecast of the next period, or null when no period is logged yet.
  /// Throws [CycleFailure] if the backend could not be asked.
  Future<CyclePrediction?> predict();
}

/// Asks the Ova backend's `POST /cycle/predict`.
class BackendPredictionService implements PredictionService {
  BackendPredictionService({
    required this.baseUrl,
    required this.userId,
    required this.accessToken,
    http.Client? client,
  }) : _client = client ?? http.Client();

  /// Long enough for a hosted backend that sleeps when idle to wake up.
  static const _timeout = Duration(seconds: 60);

  final String baseUrl;
  final String userId;

  /// The signed-in user's Supabase access token, which the backend checks
  /// before answering about [userId]. Null when no one is signed in.
  final String? Function() accessToken;
  final http.Client _client;

  @override
  Future<CyclePrediction?> predict() async {
    final http.Response response;
    try {
      response = await _client
          .post(
            Uri.parse('$baseUrl/cycle/predict'),
            headers: {
              'content-type': 'application/json',
              'authorization': 'Bearer ${accessToken() ?? ''}',
            },
            body: jsonEncode({'user_id': userId}),
          )
          .timeout(_timeout);
    } catch (_) {
      throw const CycleFailure('Could not reach the prediction service.');
    }
    // The backend answers 404 until the first period is logged.
    if (response.statusCode == 404) return null;
    if (response.statusCode != 200) {
      throw const CycleFailure(
        'Predictions are not available just now. Try again in a moment.',
      );
    }
    return CyclePrediction.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }
}
