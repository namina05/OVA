import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth/auth_providers.dart';
import 'screens/history_screen.dart';
import 'screens/home_screen.dart';
import 'screens/placeholder_screen.dart';
import 'screens/relief_prompt.dart';
import 'screens/sign_in_screen.dart';
import 'screens/therapy_screen.dart';
import 'sessions/session_providers.dart';
import 'sessions/session_record.dart';

class OvaApp extends StatelessWidget {
  const OvaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ova',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFC0504D)),
      ),
      home: const AuthGate(),
    );
  }
}

/// Shows the sign-in screen until someone is signed in.
class AuthGate extends ConsumerWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref
        .watch(currentUserProvider)
        .when(
          loading: () =>
              const Scaffold(body: Center(child: CircularProgressIndicator())),
          error: (error, _) =>
              Scaffold(body: Center(child: Text('Could not start.\n$error'))),
          // Keyed by user so nothing from one account's shell survives into another's.
          data: (user) => user == null
              ? const SignInScreen()
              : HomeShell(key: ValueKey(user.id)),
        );
  }
}

/// The five main tabs (SRS section 3.1).
class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({super.key});

  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  int _index = 0;
  StreamSubscription<SessionRecord>? _endedSessions;

  @override
  void initState() {
    super.initState();
    final recorder = ref.read(sessionRecorderProvider);
    _endedSessions = recorder.ended.listen(_askForRelief);
    recorder.ready.then((_) => _askAboutUnratedSession());
  }

  @override
  void dispose() {
    _endedSessions?.cancel();
    super.dispose();
  }

  /// A skipped rating is asked for once more, the next time the app opens
  /// (SRS FR-LOG-3).
  Future<void> _askAboutUnratedSession() async {
    final sessions = await ref.read(sessionRepositoryProvider).all();
    for (final session in sessions) {
      if (session.isFinished &&
          session.reliefScore == null &&
          session.reliefPrompts < 2) {
        return _askForRelief(session);
      }
    }
  }

  Future<void> _askForRelief(SessionRecord session) async {
    if (!mounted) return;
    final rating = await showReliefPrompt(context);
    if (!mounted) return;
    await ref
        .read(sessionRepositoryProvider)
        .save(
          session.copyWith(
            reliefScore: rating?.score,
            note: rating?.note,
            reliefPrompts: session.reliefPrompts + 1,
          ),
        );
  }

  static const _screens = [
    HomeScreen(),
    TherapyScreen(),
    PlaceholderScreen(title: 'Cycle'),
    HistoryScreen(),
    PlaceholderScreen(title: 'Chat'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _screens),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (index) => setState(() => _index = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
          NavigationDestination(
            icon: Icon(Icons.local_fire_department_outlined),
            label: 'Therapy',
          ),
          NavigationDestination(
            icon: Icon(Icons.calendar_month_outlined),
            label: 'Cycle',
          ),
          NavigationDestination(icon: Icon(Icons.history), label: 'History'),
          NavigationDestination(
            icon: Icon(Icons.chat_bubble_outline),
            label: 'Chat',
          ),
        ],
      ),
    );
  }
}
