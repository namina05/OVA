import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../belt/belt_models.dart';
import '../belt/belt_providers.dart';

class TherapyScreen extends ConsumerStatefulWidget {
  const TherapyScreen({super.key});

  @override
  ConsumerState<TherapyScreen> createState() => _TherapyScreenState();
}

class _TherapyScreenState extends ConsumerState<TherapyScreen> {
  List<HeatLevel> _levels = List.filled(zoneCount, HeatLevel.off);
  int _minutes = 20;

  Future<void> _send(Future<void> Function() command) async {
    try {
      await command();
    } on BeltException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  void _setLevel(int zone, HeatLevel level) {
    setState(() => _levels = [..._levels]..[zone] = level);
    _send(() => ref.read(beltProvider).setZoneLevels(_levels));
  }

  @override
  Widget build(BuildContext context) {
    final belt = ref.watch(beltProvider);
    final info = ref.watch(beltInfoProvider).valueOrNull;
    final telemetry = ref.watch(beltTelemetryProvider).valueOrNull;
    final state = telemetry?.state ?? SessionState.idle;
    final maxMinutes = info?.maxSession.inMinutes ?? 45;
    final anyZoneOn = _levels.any((level) => level != HeatLevel.off);

    return Scaffold(
      appBar: AppBar(title: const Text('Therapy')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          for (var zone = 0; zone < zoneCount; zone++)
            _ZoneCard(
              name: zoneNames[zone],
              level: _levels[zone],
              tempC: telemetry?.zoneTempsC[zone],
              onChanged: (level) => _setLevel(zone, level),
            ),
          const SizedBox(height: 16),
          if (state == SessionState.idle) ...[
            Text('Duration: $_minutes min', style: Theme.of(context).textTheme.titleMedium),
            Slider(
              value: _minutes.toDouble(),
              min: 5,
              max: maxMinutes.toDouble(),
              divisions: (maxMinutes - 5) ~/ 5,
              label: '$_minutes min',
              onChanged: (value) => setState(() => _minutes = value.round()),
            ),
            FilledButton.icon(
              onPressed: anyZoneOn
                  ? () => _send(() async {
                        await belt.setZoneLevels(_levels);
                        await belt.start(Duration(minutes: _minutes));
                      })
                  : null,
              icon: const Icon(Icons.play_arrow),
              label: const Text('Start session'),
            ),
          ] else ...[
            Center(
              child: Text(
                _formatRemaining(telemetry!.remaining),
                style: Theme.of(context).textTheme.displayMedium,
              ),
            ),
            Center(child: Text(state == SessionState.paused ? 'Paused' : 'Time remaining')),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () =>
                        _send(state == SessionState.paused ? belt.resume : belt.pause),
                    icon: Icon(state == SessionState.paused ? Icons.play_arrow : Icons.pause),
                    label: Text(state == SessionState.paused ? 'Resume' : 'Pause'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: Theme.of(context).colorScheme.error,
                      foregroundColor: Theme.of(context).colorScheme.onError,
                    ),
                    onPressed: () => _send(belt.stop),
                    icon: const Icon(Icons.stop),
                    label: const Text('Stop'),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

String _formatRemaining(Duration remaining) {
  final minutes = remaining.inMinutes.toString().padLeft(2, '0');
  final seconds = (remaining.inSeconds % 60).toString().padLeft(2, '0');
  return '$minutes:$seconds';
}

class _ZoneCard extends StatelessWidget {
  const _ZoneCard({
    required this.name,
    required this.level,
    required this.tempC,
    required this.onChanged,
  });

  final String name;
  final HeatLevel level;
  final double? tempC;
  final ValueChanged<HeatLevel> onChanged;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(name, style: Theme.of(context).textTheme.titleMedium),
                Text(tempC == null ? '-- °C' : '${tempC!.toStringAsFixed(1)} °C'),
              ],
            ),
            const SizedBox(height: 8),
            SegmentedButton<HeatLevel>(
              showSelectedIcon: false,
              segments: [
                for (final option in HeatLevel.values)
                  ButtonSegment(value: option, label: Text(option.label)),
              ],
              selected: {level},
              onSelectionChanged: (selection) => onChanged(selection.single),
            ),
          ],
        ),
      ),
    );
  }
}
