import 'package:flutter/material.dart';

import 'screens/placeholder_screen.dart';
import 'screens/therapy_screen.dart';

class OvaApp extends StatelessWidget {
  const OvaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ova',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFC0504D)),
      ),
      home: const HomeShell(),
    );
  }
}

/// The five main tabs (SRS section 3.1).
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _screens = [
    PlaceholderScreen(title: 'Home'),
    TherapyScreen(),
    PlaceholderScreen(title: 'Cycle'),
    PlaceholderScreen(title: 'History'),
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
          NavigationDestination(icon: Icon(Icons.local_fire_department_outlined), label: 'Therapy'),
          NavigationDestination(icon: Icon(Icons.calendar_month_outlined), label: 'Cycle'),
          NavigationDestination(icon: Icon(Icons.history), label: 'History'),
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), label: 'Chat'),
        ],
      ),
    );
  }
}
