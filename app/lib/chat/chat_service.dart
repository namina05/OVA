import 'package:supabase_flutter/supabase_flutter.dart';

import 'chat_message.dart';

/// A problem talking to the assistant, with a message fit to show the user.
class ChatFailure implements Exception {
  const ChatFailure(this.message);
  final String message;

  @override
  String toString() => 'ChatFailure: $message';
}

/// The app's only view of the assistant, so screens and tests do not depend
/// on Supabase directly.
abstract interface class ChatService {
  /// The saved conversation, oldest first.
  Future<List<ChatMessage>> history();

  /// Sends [message] and returns the saved exchange: the user's message
  /// followed by the assistant's reply.
  Future<List<ChatMessage>> send(String message);

  /// Deletes the whole conversation (SRS FR-BOT-11).
  Future<void> clear();
}

/// Talks to the `chat` Edge Function and reads the `chat_messages` table.
/// Row-level security limits every call to the signed-in user's own rows.
class SupabaseChatService implements ChatService {
  SupabaseChatService(this._client, {required this.userId});

  /// Longer conversations show only their latest messages.
  static const _historyLimit = 100;

  final SupabaseClient _client;
  final String userId;

  @override
  Future<List<ChatMessage>> history() => _guard(() async {
    final rows = await _client
        .from('chat_messages')
        .select('role, content, sources')
        .order('id', ascending: false)
        .limit(_historyLimit);
    return [for (final row in rows.reversed) ChatMessage.fromRow(row)];
  });

  @override
  Future<List<ChatMessage>> send(String message) => _guard(() async {
    final response = await _client.functions.invoke(
      'chat',
      body: {'message': message},
    );
    final rows = (response.data as Map<String, dynamic>)['messages'] as List;
    return [
      for (final row in rows) ChatMessage.fromRow(row as Map<String, dynamic>),
    ];
  });

  @override
  Future<void> clear() => _guard(
    () => _client.from('chat_messages').delete().eq('user_id', userId),
  );

  static Future<T> _guard<T>(Future<T> Function() action) async {
    try {
      return await action();
    } on FunctionException {
      throw const ChatFailure(
        'The assistant could not answer just now. Try again in a moment.',
      );
    } on PostgrestException {
      throw const ChatFailure('Something went wrong. Try again in a moment.');
    } catch (_) {
      throw const ChatFailure(
        'Could not reach the server. Check your internet connection.',
      );
    }
  }
}
