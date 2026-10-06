import 'package:flutter/material.dart';

const reliefLabels = ['No relief', 'Slight', 'Moderate', 'Good', 'Full relief'];

typedef ReliefRating = ({int score, String? note});

/// Asks how well a session worked (SRS FR-LOG-2). Returns null if the user
/// skips.
Future<ReliefRating?> showReliefPrompt(BuildContext context) {
  return showDialog<ReliefRating>(
    context: context,
    builder: (context) => const _ReliefDialog(),
  );
}

class _ReliefDialog extends StatefulWidget {
  const _ReliefDialog();

  @override
  State<_ReliefDialog> createState() => _ReliefDialogState();
}

class _ReliefDialogState extends State<_ReliefDialog> {
  final _note = TextEditingController();
  int? _score;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('How much relief did you get?'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                for (var score = 1; score <= 5; score++)
                  ChoiceChip(
                    label: Text('$score'),
                    showCheckmark: false,
                    selected: _score == score,
                    onSelected: (_) => setState(() => _score = score),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              _score == null
                  ? '1 = no relief, 5 = full relief'
                  : reliefLabels[_score! - 1],
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _note,
              maxLines: 2,
              decoration: const InputDecoration(
                labelText: 'Note (optional)',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Skip'),
        ),
        FilledButton(
          onPressed: _score == null
              ? null
              : () {
                  final note = _note.text.trim();
                  Navigator.pop(context, (
                    score: _score!,
                    note: note.isEmpty ? null : note,
                  ));
                },
          child: const Text('Save'),
        ),
      ],
    );
  }
}
