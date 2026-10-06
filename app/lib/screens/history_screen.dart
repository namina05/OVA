import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../belt/belt_models.dart';
import '../sessions/session_providers.dart';
import '../sessions/session_record.dart';
import 'relief_prompt.dart';

class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(sessionHistoryProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('History')),
      body: history.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('Could not load your sessions.\n$error')),
        data: (sessions) => sessions.isEmpty
            ? const Center(child: Text('No sessions yet'))
            : ListView.separated(
                itemCount: sessions.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (context, index) {
                  final session = sessions[index];
                  return ListTile(
                    title: Text(_formatStart(context, session.startedAt)),
                    subtitle: Text(
                      '${_formatDuration(session.actualDurationS ?? 0)} · ${_zonesUsed(session)}',
                    ),
                    trailing: Text(
                      session.reliefScore == null ? 'Not rated' : '${session.reliefScore}/5',
                    ),
                    onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => SessionDetailScreen(session: session)),
                    ),
                  );
                },
              ),
      ),
    );
  }
}

class SessionDetailScreen extends ConsumerWidget {
  const SessionDetailScreen({super.key, required this.session});

  final SessionRecord session;

  Future<void> _rate(BuildContext context, WidgetRef ref) async {
    final rating = await showReliefPrompt(context);
    if (rating == null) return;
    await ref
        .read(sessionRepositoryProvider)
        .save(session.copyWith(reliefScore: rating.score, note: rating.note));
    if (context.mounted) Navigator.pop(context);
  }

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this session?'),
        content: const Text('This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed != true) return;
    await ref.read(sessionRepositoryProvider).delete(session.id);
    if (context.mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final score = session.reliefScore;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Session'),
        actions: [
          IconButton(
            tooltip: 'Delete session',
            icon: const Icon(Icons.delete_outline),
            onPressed: () => _delete(context, ref),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            _formatStart(context, session.startedAt),
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 4),
          Text(
            '${_formatDuration(session.actualDurationS ?? 0)} of '
            '${_formatDuration(session.plannedDurationS)} planned · ${session.endReason!.label}',
          ),
          const SizedBox(height: 16),
          for (var zone = 0; zone < zoneCount; zone++) _ZoneRow(zone: zone, session: session),
          const SizedBox(height: 16),
          if (score == null)
            FilledButton(
              onPressed: () => _rate(context, ref),
              child: const Text('Rate this session'),
            )
          else
            Text(
              'Relief: $score/5 (${reliefLabels[score - 1]})',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          if (session.note != null) ...[
            const SizedBox(height: 8),
            Text(session.note!),
          ],
        ],
      ),
    );
  }
}

class _ZoneRow extends StatelessWidget {
  const _ZoneRow({required this.zone, required this.session});

  final int zone;
  final SessionRecord session;

  @override
  Widget build(BuildContext context) {
    final summary = session.zones[zone];
    final avg = summary.avgTempC;
    final details = summary.secondsActive == 0
        ? 'Not used'
        : '${summary.level.label} · ${_formatDuration(summary.secondsActive)}'
            '${avg == null ? '' : ' · avg ${avg.toStringAsFixed(1)} °C'}';

    return ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      title: Text(zoneNames[zone]),
      trailing: Text(details),
    );
  }
}

String _zonesUsed(SessionRecord session) {
  final used = [
    for (var zone = 0; zone < zoneCount; zone++)
      if (session.zones[zone].secondsActive > 0)
        '${zoneNames[zone]} ${session.zones[zone].level.label}',
  ];
  return used.isEmpty ? 'No zones heated' : used.join(', ');
}

String _formatStart(BuildContext context, DateTime startedAt) {
  final localizations = MaterialLocalizations.of(context);
  return '${localizations.formatMediumDate(startedAt)}, '
      '${localizations.formatTimeOfDay(TimeOfDay.fromDateTime(startedAt))}';
}

String _formatDuration(int seconds) {
  if (seconds < 60) return '$seconds s';
  final minutes = seconds ~/ 60;
  final rest = seconds % 60;
  return rest == 0 ? '$minutes min' : '$minutes min $rest s';
}
