import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../cycle/cycle_prediction.dart';
import '../cycle/cycle_providers.dart';
import '../cycle/cycle_service.dart';
import '../cycle/period.dart';
import '../profile/profile_providers.dart';

/// The user's logged periods and the backend's forecast of the next one.
class CycleScreen extends ConsumerWidget {
  const CycleScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final periods = ref.watch(periodsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Cycle')),
      body: periods.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load your periods.'),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: () => ref.invalidate(periodsProvider),
                child: const Text('Try again'),
              ),
            ],
          ),
        ),
        data: (periods) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const NextPeriodCard(),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: () => openPeriodCalendar(context),
              icon: const Icon(Icons.calendar_month_outlined),
              label: Text(periods.isEmpty ? 'Log period' : 'Edit period dates'),
            ),
            const SizedBox(height: 24),
            Text('Your periods', style: theme.textTheme.titleLarge),
            const SizedBox(height: 8),
            if (periods.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text('No periods logged yet'),
              )
            else
              Card(
                clipBehavior: Clip.antiAlias,
                child: Column(
                  children: [
                    for (final period in periods)
                      ListTile(
                        leading: CircleAvatar(
                          backgroundColor: theme.colorScheme.primaryContainer,
                          child: Icon(
                            Icons.water_drop_outlined,
                            color: theme.colorScheme.primary,
                          ),
                        ),
                        title: Text(_formatRange(context, period)),
                        subtitle: Text(_formatLength(period.lengthDays)),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () =>
                            openPeriodCalendar(context, period.startDate),
                      ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Opens the calendar for marking period days, on the month of [showing] or
/// the current month.
void openPeriodCalendar(BuildContext context, [DateTime? showing]) {
  Navigator.push(
    context,
    MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => PeriodCalendarScreen(showing: showing),
    ),
  );
}

/// When the next period is expected, once there is a period to predict from.
class NextPeriodCard extends ConsumerWidget {
  const NextPeriodCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final prediction = ref.watch(cyclePredictionProvider);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: const BorderRadius.all(Radius.circular(28)),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color.lerp(colors.primary, Colors.white, 0.25)!,
            colors.primary,
          ],
        ),
        boxShadow: [
          BoxShadow(
            color: colors.primary.withValues(alpha: 0.25),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      // Everything on the card is drawn in the colour that reads on it.
      child: DefaultTextStyle.merge(
        style: TextStyle(color: colors.onPrimary),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.water_drop, size: 18, color: colors.onPrimary),
                const SizedBox(width: 6),
                Text(
                  'Next period',
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: colors.onPrimary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            ...prediction.when(
              loading: () => [
                Center(
                  child: CircularProgressIndicator(color: colors.onPrimary),
                ),
              ],
              // Logging still works when the prediction cannot be fetched.
              error: (error, _) => [
                Text(
                  error is CycleFailure
                      ? error.message
                      : 'Predictions are not available just now.',
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: colors.onPrimary,
                    side: BorderSide(color: colors.onPrimary),
                  ),
                  onPressed: () => ref.invalidate(cyclePredictionProvider),
                  child: const Text('Try again'),
                ),
              ],
              data: (prediction) => prediction == null
                  ? const [
                      Text(
                        'Log the first day of a period to see when the next '
                        'one is expected.',
                      ),
                    ]
                  : _details(context, prediction),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _details(BuildContext context, CyclePrediction prediction) {
    final theme = Theme.of(context);
    final onCard = theme.colorScheme.onPrimary;
    final localizations = MaterialLocalizations.of(context);
    final small = theme.textTheme.bodySmall?.copyWith(
      color: onCard.withValues(alpha: 0.85),
    );

    return [
      Text(
        _formatCountdown(prediction),
        style: theme.textTheme.displaySmall?.copyWith(color: onCard),
      ),
      Text(
        localizations.formatMediumDate(prediction.predictedStart),
        style: theme.textTheme.titleMedium?.copyWith(color: onCard),
      ),
      const SizedBox(height: 12),
      Text(
        'Give or take ${_days(prediction.rangeDays)} · '
        'about ${_days(prediction.predictedPeriodLength)} long',
      ),
      if (prediction.ovulationDate != null) ...[
        const SizedBox(height: 4),
        Text(_formatOvulation(localizations, prediction)),
      ],
      if (prediction.highPainDates.isNotEmpty) ...[
        const SizedBox(height: 4),
        Text(
          'Most pain expected: '
          '${prediction.highPainDates.map(localizations.formatShortMonthDay).join(', ')}',
        ),
      ],
      for (final alert in prediction.alerts) ...[
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: onCard.withValues(alpha: 0.18),
            borderRadius: const BorderRadius.all(Radius.circular(16)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                alert.title,
                style: theme.textTheme.titleSmall?.copyWith(color: onCard),
              ),
              Text(alert.advice),
            ],
          ),
        ),
      ],
      const SizedBox(height: 12),
      Text(prediction.explanation, style: small),
      const SizedBox(height: 8),
      Text(prediction.notice, style: small),
    ];
  }
}

/// A scrolling calendar where tapping a day marks or unmarks it as a period
/// day. Nothing is stored until Save.
class PeriodCalendarScreen extends ConsumerStatefulWidget {
  const PeriodCalendarScreen({super.key, this.showing});

  /// A day in the month to open on. The current month when null.
  final DateTime? showing;

  @override
  ConsumerState<PeriodCalendarScreen> createState() =>
      _PeriodCalendarScreenState();
}

class _PeriodCalendarScreenState extends ConsumerState<PeriodCalendarScreen> {
  /// How far back a period can be logged.
  static const _months = 60;
  static const _monthHeaderHeight = 48.0;

  /// Days marked when nothing says how long the user's periods last.
  static const _defaultPeriodLength = 5;

  final _today = DateUtils.dateOnly(DateTime.now());
  late final Set<DateTime> _days = daysOfPeriods(
    ref.read(periodsProvider).valueOrNull ?? const [],
    _today,
  );
  ScrollController? _scroll;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _scroll?.dispose();
    super.dispose();
  }

  void _toggle(DateTime day) {
    setState(() {
      if (_days.remove(day)) return;
      _days.add(day);
      // A day on its own starts a new period, so the days a period usually
      // lasts are marked with it, as far as today.
      final alone =
          !_days.contains(addDays(day, -1)) && !_days.contains(addDays(day, 1));
      if (!alone) return;
      final length =
          ref.read(profileProvider).valueOrNull?.typicalPeriodLength ??
          _defaultPeriodLength;
      for (var i = 1; i < length; i++) {
        final next = addDays(day, i);
        if (next.isAfter(_today) || _days.contains(addDays(next, 1))) break;
        _days.add(next);
      }
    });
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(periodsProvider.notifier).setDays(_days);
      if (mounted) Navigator.pop(context);
    } on CycleFailure catch (failure) {
      if (mounted) setState(() => _error = failure.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final prediction = ref.watch(cyclePredictionProvider).valueOrNull;

    return Scaffold(
      appBar: AppBar(
        leading: const CloseButton(),
        title: const Text('Edit period dates'),
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          children: [
            const _WeekdayHeader(),
            const Divider(height: 16),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final cell = constraints.maxWidth / DateTime.daysPerWeek;
                  // Every month takes the room of six weeks, so the list
                  // can open on any month without measuring the others.
                  final monthHeight = _monthHeaderHeight + 6 * cell;
                  final showing = widget.showing ?? _today;
                  _scroll ??= ScrollController(
                    initialScrollOffset:
                        monthHeight *
                        DateUtils.monthDelta(
                          showing,
                          _today,
                        ).clamp(0, _months - 1),
                  );
                  // Reversed, so the current month sits at the bottom and
                  // earlier months are above it.
                  return ListView.builder(
                    controller: _scroll,
                    reverse: true,
                    itemCount: _months,
                    itemExtent: monthHeight,
                    itemBuilder: (context, index) => _Month(
                      month: DateTime(_today.year, _today.month - index),
                      cell: cell,
                      headerHeight: _monthHeaderHeight,
                      today: _today,
                      marked: _days,
                      prediction: prediction,
                      onTap: _busy ? null : _toggle,
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const _Legend(),
              const SizedBox(height: 12),
              if (_error != null) ...[
                Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
                const SizedBox(height: 8),
              ],
              FilledButton(
                onPressed: _busy ? null : _save,
                child: const Text('Save'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// This month's period days, shown where the user lands. Tapping it opens the
/// calendar to mark days.
class PeriodCalendarCard extends ConsumerWidget {
  const PeriodCalendarCard({super.key});

  static const _monthHeaderHeight = 40.0;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final today = DateUtils.dateOnly(DateTime.now());
    final periods = ref.watch(periodsProvider).valueOrNull ?? const [];
    final prediction = ref.watch(cyclePredictionProvider).valueOrNull;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const _WeekdayHeader(),
            LayoutBuilder(
              builder: (context, constraints) => _Month(
                month: DateTime(today.year, today.month),
                cell: constraints.maxWidth / DateTime.daysPerWeek,
                headerHeight: _monthHeaderHeight,
                today: today,
                marked: daysOfPeriods(periods, today),
                prediction: prediction,
                onTap: (_) => openPeriodCalendar(context),
              ),
            ),
            const _Legend(),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: () => openPeriodCalendar(context),
              icon: const Icon(Icons.calendar_month_outlined),
              label: Text(periods.isEmpty ? 'Log period' : 'Edit period dates'),
            ),
          ],
        ),
      ),
    );
  }
}

/// The initials of the days of the week, above the calendar's columns.
class _WeekdayHeader extends StatelessWidget {
  const _WeekdayHeader();

  @override
  Widget build(BuildContext context) {
    final localizations = MaterialLocalizations.of(context);

    return Row(
      children: [
        for (var i = 0; i < DateTime.daysPerWeek; i++)
          Expanded(
            child: Center(
              child: Text(
                localizations
                    .narrowWeekdays[(localizations.firstDayOfWeekIndex + i) %
                    DateTime.daysPerWeek],
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ),
          ),
      ],
    );
  }
}

/// One month of the period calendar.
class _Month extends StatelessWidget {
  const _Month({
    required this.month,
    required this.cell,
    required this.headerHeight,
    required this.today,
    required this.marked,
    required this.prediction,
    required this.onTap,
  });

  /// The first day of the month.
  final DateTime month;
  final double cell;
  final double headerHeight;
  final DateTime today;
  final Set<DateTime> marked;
  final CyclePrediction? prediction;
  final void Function(DateTime day)? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final localizations = MaterialLocalizations.of(context);
    final days = DateUtils.getDaysInMonth(month.year, month.month);
    // Empty cells before the 1st, so it falls under its weekday.
    final blanks =
        (month.weekday - localizations.firstDayOfWeekIndex) %
        DateTime.daysPerWeek;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          height: headerHeight,
          child: Align(
            alignment: Alignment.bottomLeft,
            child: Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                localizations.formatMonthYear(month),
                style: theme.textTheme.titleMedium,
              ),
            ),
          ),
        ),
        for (
          var first = 1 - blanks;
          first <= days;
          first += DateTime.daysPerWeek
        )
          Row(
            children: [
              for (var day = first; day < first + DateTime.daysPerWeek; day++)
                Expanded(
                  child: day < 1 || day > days
                      ? SizedBox(height: cell)
                      : _Day(
                          date: DateTime(month.year, month.month, day),
                          size: cell,
                          today: today,
                          marked: marked,
                          prediction: prediction,
                          onTap: onTap,
                        ),
                ),
            ],
          ),
      ],
    );
  }
}

/// A day of the period calendar: filled when marked as a period day, tinted
/// when a period is predicted, ringed when it is today.
class _Day extends StatelessWidget {
  const _Day({
    required this.date,
    required this.size,
    required this.today,
    required this.marked,
    required this.prediction,
    required this.onTap,
  });

  final DateTime date;
  final double size;
  final DateTime today;
  final Set<DateTime> marked;
  final CyclePrediction? prediction;
  final void Function(DateTime day)? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final isMarked = marked.contains(date);
    final isFuture = date.isAfter(today);
    final isOvulation = date == prediction?.ovulationDate;
    final fill = isMarked
        ? colors.primary
        : (prediction?.days.contains(date) ?? false)
        ? colors.primaryContainer
        : (prediction?.fertileDays.contains(date) ?? false)
        ? _fertileColor
        : Colors.transparent;

    return SizedBox(
      height: size,
      child: Padding(
        padding: const EdgeInsets.all(4),
        child: Material(
          color: fill,
          shape: CircleBorder(
            side: date == today
                ? BorderSide(color: colors.primary, width: 2)
                : isOvulation
                ? const BorderSide(color: _ovulationColor, width: 2)
                : BorderSide.none,
          ),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            key: ValueKey('day-${dateOnly(date)}'),
            // A period cannot be logged ahead of time.
            onTap: isFuture || onTap == null ? null : () => onTap!(date),
            child: Center(
              child: Text(
                '${date.day}',
                style: TextStyle(
                  color: isMarked
                      ? colors.onPrimary
                      : isFuture && fill == Colors.transparent
                      ? colors.onSurface.withValues(alpha: 0.38)
                      : colors.onSurface,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Fertile days are shown in a calm green, apart from the rose of periods.
const _fertileColor = Color(0xFFD5EFE6);
const _ovulationColor = Color(0xFF3E9E85);

/// What the calendar's colours mean.
class _Legend extends StatelessWidget {
  const _Legend();

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    Widget item(String label, Color fill, [Color? ring]) => Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            color: fill,
            shape: BoxShape.circle,
            border: ring == null ? null : Border.all(color: ring, width: 2),
          ),
        ),
        const SizedBox(width: 4),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );

    return Wrap(
      spacing: 12,
      runSpacing: 4,
      children: [
        item('Period', colors.primary),
        item('Predicted', colors.primaryContainer),
        item('Fertile', _fertileColor),
        item('Ovulation', _fertileColor, _ovulationColor),
      ],
    );
  }
}

String _formatOvulation(
  MaterialLocalizations localizations,
  CyclePrediction prediction,
) {
  final ovulation = localizations.formatShortMonthDay(
    prediction.ovulationDate!,
  );
  final start = prediction.fertileStart, end = prediction.fertileEnd;
  return start == null || end == null
      ? 'Estimated ovulation: $ovulation'
      : 'Estimated ovulation: $ovulation · fertile '
            '${localizations.formatShortMonthDay(start)} – '
            '${localizations.formatShortMonthDay(end)}';
}

String _formatRange(BuildContext context, Period period) {
  final localizations = MaterialLocalizations.of(context);
  final start = localizations.formatMediumDate(period.startDate);
  final end = period.endDate;
  return end == null
      ? 'Started $start'
      : '$start – ${localizations.formatMediumDate(end)}';
}

String _formatLength(int? days) => days == null ? 'Ongoing' : _days(days);

String _formatCountdown(CyclePrediction prediction) {
  final days = prediction.daysUntilStart;
  if (days == 0) return 'Expected today';
  return days > 0 ? 'In ${_days(days)}' : 'Expected ${_days(-days)} ago';
}

String _days(int count) => count == 1 ? '1 day' : '$count days';
