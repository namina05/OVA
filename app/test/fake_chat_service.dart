import 'package:ova/chat/chat_message.dart';
import 'package:ova/chat/chat_service.dart';

/// An in-memory assistant for tests.
class FakeChatService implements ChatService {
  FakeChatService({List<ChatMessage>? saved}) : saved = saved ?? [];

  final List<ChatMessage> saved;

  /// What the assistant says next.
  ChatMessage reply = const ChatMessage(fromUser: false, content: 'A reply.');

  /// When true every call fails, as it would with no internet.
  bool offline = false;

  @override
  Future<List<ChatMessage>> history() async {
    _checkOnline();
    return List.of(saved);
  }

  @override
  Future<List<ChatMessage>> send(String message) async {
    _checkOnline();
    final exchange = [ChatMessage(fromUser: true, content: message), reply];
    saved.addAll(exchange);
    return exchange;
  }

  @override
  Future<void> clear() async {
    _checkOnline();
    saved.clear();
  }

  void _checkOnline() {
    if (offline) throw const ChatFailure('Could not reach the server.');
  }
}
