import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'session_record.dart';

/// Where the session log is kept as one JSON document.
abstract interface class SessionStore {
  Future<String?> read();
  Future<void> write(String contents);
}

/// Keeps the log in a file on the phone, so sessions survive with no internet
/// (SRS NFR-REL-1).
class FileSessionStore implements SessionStore {
  FileSessionStore(this._file);

  final Future<File> Function() _file;

  @override
  Future<String?> read() async {
    final file = await _file();
    return await file.exists() ? file.readAsString() : null;
  }

  @override
  Future<void> write(String contents) async {
    // Write beside the real file, then swap, so a crash mid-write cannot
    // leave a half-written log.
    final file = await _file();
    final temp = File('${file.path}.tmp');
    await temp.writeAsString(contents, flush: true);
    await temp.rename(file.path);
  }
}

class MemorySessionStore implements SessionStore {
  String? contents;

  @override
  Future<String?> read() async => contents;

  @override
  Future<void> write(String contents) async => this.contents = contents;
}

class SessionRepository {
  SessionRepository(this._store);

  final SessionStore _store;
  final _changes = StreamController<void>.broadcast();
  Map<String, SessionRecord>? _records;
  Future<void> _queue = Future.value();

  /// Fires after every save or delete.
  Stream<void> get changes => _changes.stream;

  /// All sessions, newest first.
  Future<List<SessionRecord>> all() => _enqueue((records) async =>
      records.values.toList()..sort((a, b) => b.startedAt.compareTo(a.startedAt)));

  Future<void> save(SessionRecord record) => _enqueue((records) async {
        records[record.id] = record;
        await _persist(records);
      });

  Future<void> delete(String id) => _enqueue((records) async {
        if (records.remove(id) != null) await _persist(records);
      });

  /// Runs operations one at a time, in the order they were requested.
  Future<T> _enqueue<T>(Future<T> Function(Map<String, SessionRecord> records) action) {
    final result = _queue.then((_) async => action(await _load()));
    _queue = result.then((_) {}, onError: (_) {});
    return result;
  }

  Future<Map<String, SessionRecord>> _load() async {
    final cached = _records;
    if (cached != null) return cached;
    final contents = await _store.read();
    final records = <String, SessionRecord>{};
    if (contents != null) {
      for (final json in jsonDecode(contents) as List) {
        final record = SessionRecord.fromJson(json as Map<String, dynamic>);
        records[record.id] = record;
      }
    }
    return _records = records;
  }

  Future<void> _persist(Map<String, SessionRecord> records) async {
    await _store.write(jsonEncode([for (final record in records.values) record.toJson()]));
    _changes.add(null);
  }
}
