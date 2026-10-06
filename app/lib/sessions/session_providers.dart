import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';

import '../belt/belt_providers.dart';
import 'session_record.dart';
import 'session_recorder.dart';
import 'session_repository.dart';

final sessionRepositoryProvider = Provider<SessionRepository>((ref) {
  return SessionRepository(FileSessionStore(() async {
    final directory = await getApplicationDocumentsDirectory();
    return File('${directory.path}/sessions.json');
  }));
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
final sessionHistoryProvider = StreamProvider<List<SessionRecord>>((ref) async* {
  final repository = ref.watch(sessionRepositoryProvider);
  Future<List<SessionRecord>> finished() async =>
      [for (final record in await repository.all()) if (record.isFinished) record];

  yield await finished();
  await for (final _ in repository.changes) {
    yield await finished();
  }
});
