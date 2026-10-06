import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ova/chat/chat_message.dart';
import 'package:ova/chat/chat_providers.dart';
import 'package:ova/screens/chat_screen.dart';

import 'fake_chat_service.dart';

void main() {
  late FakeChatService chat;

  Future<void> pumpChat(WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [chatServiceProvider.overrideWithValue(chat)],
        child: const MaterialApp(home: ChatScreen()),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> ask(WidgetTester tester, String question) async {
    await tester.enterText(find.byType(TextField), question);
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();
  }

  setUp(() => chat = FakeChatService());

  testWidgets('a question shows with its answer and the cited sources', (
    tester,
  ) async {
    chat.reply = const ChatMessage(
      fromUser: false,
      content: 'A heat pad can ease cramps [1].',
      sources: [
        ChatSource(
          title: 'Period pain',
          url: 'https://example.org/period-pain',
          attribution: 'Contains public sector information',
        ),
      ],
    );
    await pumpChat(tester);

    await ask(tester, 'What helps with cramps?');

    expect(find.text('What helps with cramps?'), findsOneWidget);
    expect(find.text('A heat pad can ease cramps [1].'), findsOneWidget);
    expect(
      find.text('[1] Period pain\nContains public sector information'),
      findsOneWidget,
    );
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      '',
    );
  });

  testWidgets('an earlier conversation is shown when the screen opens', (
    tester,
  ) async {
    chat = FakeChatService(
      saved: const [
        ChatMessage(fromUser: true, content: 'Why do periods hurt?'),
        ChatMessage(fromUser: false, content: 'The womb tightens.'),
      ],
    );
    await pumpChat(tester);

    expect(find.text('Why do periods hurt?'), findsOneWidget);
    expect(find.text('The womb tightens.'), findsOneWidget);
  });

  testWidgets('a question that fails to send goes back in the box', (
    tester,
  ) async {
    await pumpChat(tester);
    chat.offline = true;

    await ask(tester, 'What helps with cramps?');

    expect(find.text('Could not reach the server.'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      'What helps with cramps?',
    );
    expect(chat.saved, isEmpty);
  });

  testWidgets('clearing the conversation removes it after confirming', (
    tester,
  ) async {
    await pumpChat(tester);
    await ask(tester, 'What helps with cramps?');

    await tester.tap(find.byTooltip('Clear conversation'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clear'));
    await tester.pumpAndSettle();

    expect(find.text('What helps with cramps?'), findsNothing);
    expect(chat.saved, isEmpty);
    expect(find.byTooltip('Clear conversation'), findsNothing);
  });

  testWidgets('a history that fails to load can be retried', (tester) async {
    chat.offline = true;
    await pumpChat(tester);
    expect(find.text('Could not reach the server.'), findsOneWidget);

    chat.offline = false;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Ask a question about periods'), findsOneWidget);
  });
}
