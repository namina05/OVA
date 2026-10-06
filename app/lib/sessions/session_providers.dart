import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../auth/auth_providers.dart';
import '../belt/belt_providers.dart';
import 'session_record.dart';
import 'session_recorder.dart';
import 'session_repository.dart';

final sessionRepositoryProvider = Provider<SessionRepository>((ref) {
  // Watch only the id: token refreshes re-emit the user, and must not replace
  // the repository (and with it the recorder) in the middle of a session.
  final userId = ref.watch(
    currentUserProvider.select((user) => user.valueOrNull?.id),
  );
  if (userId == null) throw StateError('No one is signed in');
  return SessionRepository(
    SupabaseSessionStore(Supabase.instance.client, userId: userId),
  );
});

final sessionRecorderProvider = Provider<SessionRecorder>((ref) {
  final recorder = SessionRecorder(
    belt: ref.watch(beltProvider),
    repository: ref.watch(sessionRepositoryProvider),
  )..start();
  ref.onDispose(recorder.dispose);
  return recorder;
});

/// Finished sessions, newest first, refreshed whenever the log changes.
final sessionHistoryProvider = StreamProvider<List<SessionRecord>>((
  ref,
) async* {
  final repository = ref.watch(sessionRepositoryProvider);
  Future<List<SessionRecord>> finished() async => [
    for (final record in await repository.all())
      if (record.isFinished) record,
  ];

  yield await finished();
  await for (final _ in repository.changes) {
    yield await finished();
  }
});
