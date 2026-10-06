/// A knowledge document an assistant reply cites.
class ChatSource {
  const ChatSource({
    required this.title,
    required this.url,
    required this.attribution,
  });

  factory ChatSource.fromJson(Map<String, dynamic> json) => ChatSource(
    title: json['title'] as String,
    url: json['source'] as String? ?? '',
    attribution: json['attribution'] as String? ?? '',
  );

  final String title;
  final String url;

  /// The credit line the document's licence asks to be shown with it.
  final String attribution;
}

/// One message in the conversation with the assistant.
class ChatMessage {
  const ChatMessage({
    required this.fromUser,
    required this.content,
    this.sources = const [],
  });

  /// Reads a row of the `chat_messages` table.
  factory ChatMessage.fromRow(Map<String, dynamic> row) => ChatMessage(
    fromUser: row['role'] == 'user',
    content: row['content'] as String,
    sources: [
      for (final source in row['sources'] as List? ?? const [])
        ChatSource.fromJson(source as Map<String, dynamic>),
    ],
  );

  final bool fromUser;
  final String content;

  /// In citation order: a "[1]" in [content] refers to the first source.
  final List<ChatSource> sources;
}
