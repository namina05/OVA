import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../chat/chat_message.dart';
import '../chat/chat_providers.dart';
import '../chat/chat_service.dart';

/// Conversation with the assistant, which answers from the vetted knowledge
/// base and lists the documents it used.
class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();

  List<ChatMessage>? _messages;
  String? _loadError;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loadError = null);
    try {
      final messages = await ref.read(chatServiceProvider).history();
      if (!mounted) return;
      setState(() => _messages = messages);
      _scrollToEnd();
    } on ChatFailure catch (failure) {
      if (mounted) setState(() => _loadError = failure.message);
    }
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    final messages = _messages;
    if (text.isEmpty || _sending || messages == null) return;

    // The question shows at once; the saved exchange replaces it when the
    // reply arrives.
    final asked = ChatMessage(fromUser: true, content: text);
    _input.clear();
    setState(() {
      _messages = [...messages, asked];
      _sending = true;
    });
    _scrollToEnd();

    try {
      final exchange = await ref.read(chatServiceProvider).send(text);
      if (!mounted) return;
      setState(() => _messages = [...messages, ...exchange]);
    } on ChatFailure catch (failure) {
      if (!mounted) return;
      // Nothing was saved, so the question goes back in the box to resend.
      setState(() => _messages = messages);
      _input.text = text;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(failure.message)));
    } finally {
      if (mounted) setState(() => _sending = false);
      _scrollToEnd();
    }
  }

  Future<void> _clear() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Clear this conversation?'),
        content: const Text('This cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Clear'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(chatServiceProvider).clear();
      if (mounted) setState(() => _messages = []);
    } on ChatFailure catch (failure) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(failure.message)));
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final messages = _messages;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Chat'),
        actions: [
          if (messages != null && messages.isNotEmpty && !_sending)
            IconButton(
              tooltip: 'Clear conversation',
              icon: const Icon(Icons.delete_outline),
              onPressed: _clear,
            ),
        ],
      ),
      body: Column(
        children: [
          Expanded(child: _buildConversation(context, messages)),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 8, 4),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _input,
                    enabled: messages != null,
                    minLines: 1,
                    maxLines: 4,
                    maxLength: 1000,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                    decoration: const InputDecoration(
                      hintText: 'Ask about periods or period pain',
                      border: InputBorder.none,
                      counterText: '',
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Send',
                  icon: const Icon(Icons.send),
                  onPressed: _sending || messages == null ? null : _send,
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              'General information, not medical advice.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildConversation(BuildContext context, List<ChatMessage>? messages) {
    if (_loadError != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_loadError!, textAlign: TextAlign.center),
            const SizedBox(height: 8),
            OutlinedButton(onPressed: _load, child: const Text('Try again')),
          ],
        ),
      );
    }
    if (messages == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (messages.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Ask a question about periods or period pain. Answers come from '
            'vetted health sources, which are listed under each reply.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return ListView(
      controller: _scroll,
      padding: const EdgeInsets.all(16),
      children: [
        for (final message in messages) _Bubble(message: message),
        if (_sending)
          const Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: EdgeInsets.all(8),
              child: SizedBox.square(
                dimension: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          ),
      ],
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;

    return Align(
      alignment: message.fromUser
          ? Alignment.centerRight
          : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.8,
        ),
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: message.fromUser
              ? colors.primaryContainer
              : colors.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(message.content),
            if (message.sources.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Sources', style: theme.textTheme.labelMedium),
              for (final (index, source) in message.sources.indexed)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    '[${index + 1}] ${source.title}\n${source.attribution}',
                    style: theme.textTheme.bodySmall,
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
