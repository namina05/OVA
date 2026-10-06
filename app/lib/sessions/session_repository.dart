import 'dart:async';

import 'package:supabase_flutter/supabase_flutter.dart';

import 'session_record.dart';

/// Where sessions are kept.
abstract interface class SessionStore {
  Future<List<SessionRecord>> loadAll();
  Future<void> upsert(SessionRecord record);
  Future<void> delete(String id);
}

/// Keeps one account's sessions in the Supabase `sessions` and
/// `session_zones` tables. Row-level security limits every call to the
/// signed-in user's own rows.
class SupabaseSessionStore implements SessionStore {
  SupabaseSessionStore(this._client, {required this.userId});

  final SupabaseClient _client;
  final String userId;

  @override
  Future<List<SessionRecord>> loadAll() async {
    final rows = await _client
        .from('sessions')
        .select('*, session_zones(*)')
        .order('started_at', ascending: false);
    return [for (final row in rows) SessionRecord.fromRow(row)];
  }

  // The session row goes first: zone rows are only accepted for a session
  // the user already owns. Both writes are upserts, so repeating one after a
  // failure is safe.
  @override
  Future<void> upsert(SessionRecord record) async {
    await _client.from('sessions').upsert(record.toRow(userId: userId));
    await _client
        .from('session_zones')
        .upsert(record.toZoneRows(), onConflict: 'session_id,zone');
  }

  @override
  Future<void> delete(String id) =>
      _client.from('sessions').delete().eq('id', id);
}

class MemorySessionStore implements SessionStore {
  final Map<String, SessionRecord> records = {};

  /// When true every call fails, as it would with no internet.
  bool offline = false;

  @override
  Future<List<SessionRecord>> loadAll() async {
    _checkOnline();
    return records.values.toList();
  }

  @override
  Future<void> upsert(SessionRecord record) async {
    _checkOnline();
    records[record.id] = record;
  }

  @override
  Future<void> delete(String id) async {
    _checkOnline();
    records.remove(id);
  }

  void _checkOnline() {
    if (offline) throw Exception('offline');
  }
}

/// The app's session log. Changes show in the app at once and are sent to
/// the [SessionStore]; anything that fails to send is kept in memory and
/// sent again on the next save, delete or read.
class SessionRepository {
  SessionRepository(this._store);

  final SessionStore _store;
  final _changes = StreamController<void>.broadcast();
  final Map<String, SessionRecord> _records = {};
  final Set<String> _unsaved = {};
  final Set<String> _undeleted = {};
  bool _loaded = false;
  Future<void> _queue = Future.value();

  /// Fires after every save or delete.
  Stream<void> get changes => _changes.stream;

  /// True while some change has not reached the store yet.
  bool get hasUnsentChanges => _unsaved.isNotEmpty || _undeleted.isNotEmpty;

  /// All sessions, newest first.
  Future<List<SessionRecord>> all() => _enqueue(() async {
    await _send();
    return _records.values.toList()
      ..sort((a, b) => b.startedAt.compareTo(a.startedAt));
  });

  Future<void> save(SessionRecord record) => _enqueue(() async {
    _records[record.id] = record;
    _unsaved.add(record.id);
    _changes.add(null);
    await _send();
  });

  Future<void> delete(String id) => _enqueue(() async {
    if (_records.remove(id) == null) return;
    _unsaved.remove(id);
    _undeleted.add(id);
    _changes.add(null);
    await _send();
  });

  /// Runs operations one at a time, in the order they were requested.
  Future<T> _enqueue<T>(Future<T> Function() action) {
    final result = _queue.then((_) async {
      await _load();
      return action();
    });
    _queue = result.then((_) {}, onError: (_) {});
    return result;
  }

  /// Fetches the stored sessions once. If the store cannot be reached the
  /// app carries on with what it has and tries again on the next operation.
  Future<void> _load() async {
    if (_loaded) return;
    try {
      for (final record in await _store.loadAll()) {
        final changedHere =
            _unsaved.contains(record.id) || _undeleted.contains(record.id);
        if (!changedHere) _records[record.id] = record;
      }
      _loaded = true;
      _changes.add(null);
    } catch (_) {
      // Still unreachable; _loaded stays false.
    }
  }

  /// Sends pending changes, stopping at the first failure so an offline
  /// phone does not wait on every one.
  Future<void> _send() async {
    try {
      for (final id in _undeleted.toList()) {
        await _store.delete(id);
        _undeleted.remove(id);
      }
      for (final id in _unsaved.toList()) {
        await _store.upsert(_records[id]!);
        _unsaved.remove(id);
      }
    } catch (_) {
      // Left pending for the next attempt.
    }
  }
}
