import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../profile/profile.dart';
import '../profile/profile_service.dart';

/// The profile questions, used both for first-time setup and for editing.
///
/// With no [initial] profile it also asks for consent, which is recorded
/// once and not asked again.
class ProfileForm extends StatefulWidget {
  const ProfileForm({
    super.key,
    this.initial,
    required this.submitLabel,
    required this.onSubmit,
  });

  final Profile? initial;
  final String submitLabel;

  /// Stores the profile. A [ProfileFailure] it throws is shown on the form.
  final Future<void> Function(Profile profile) onSubmit;

  @override
  State<ProfileForm> createState() => _ProfileFormState();
}

class _ProfileFormState extends State<ProfileForm> {
  final _formKey = GlobalKey<FormState>();
  late final _name = TextEditingController(text: widget.initial?.displayName);
  late final _cycleLength = TextEditingController(
    text: widget.initial?.typicalCycleLength?.toString(),
  );
  late final _periodLength = TextEditingController(
    text: widget.initial?.typicalPeriodLength?.toString(),
  );
  final _dateOfBirthText = TextEditingController();

  late DateTime? _dateOfBirth = widget.initial?.dateOfBirth;
  late bool _chatbotDataAccess = widget.initial?.chatbotDataAccess ?? true;
  bool _consented = false;
  bool _busy = false;
  String? _error;

  bool get _settingUp => widget.initial == null;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _showDateOfBirth();
  }

  @override
  void dispose() {
    _name.dispose();
    _cycleLength.dispose();
    _periodLength.dispose();
    _dateOfBirthText.dispose();
    super.dispose();
  }

  void _showDateOfBirth() {
    final date = _dateOfBirth;
    _dateOfBirthText.text = date == null
        ? ''
        : MaterialLocalizations.of(context).formatMediumDate(date);
  }

  Future<void> _pickDateOfBirth() async {
    final today = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      helpText: 'Date of birth',
      initialDate: _dateOfBirth ?? DateTime(today.year - 20),
      firstDate: DateTime(1900),
      lastDate: today,
    );
    if (picked == null || !mounted) return;
    setState(() => _dateOfBirth = picked);
    _showDateOfBirth();
  }

  Future<void> _submit() async {
    setState(() => _error = null);
    if (!_formKey.currentState!.validate()) return;
    if (_settingUp && !_consented) {
      setState(() => _error = 'Tick the box to agree before continuing.');
      return;
    }

    setState(() => _busy = true);
    try {
      await widget.onSubmit(
        Profile(
          displayName: _name.text.trim(),
          dateOfBirth: _dateOfBirth!,
          consentAt: widget.initial?.consentAt ?? DateTime.now(),
          typicalCycleLength: int.tryParse(_cycleLength.text),
          typicalPeriodLength: int.tryParse(_periodLength.text),
          chatbotDataAccess: _chatbotDataAccess,
        ),
      );
    } on ProfileFailure catch (failure) {
      if (mounted) setState(() => _error = failure.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Accepts an empty box, or a whole number of days from [min] to [max].
  static String? Function(String?) _optionalDays(int min, int max) => (value) {
    if (value == null || value.isEmpty) return null;
    final days = int.tryParse(value);
    return days != null && days >= min && days <= max
        ? null
        : 'Enter $min to $max days, or leave empty';
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextFormField(
            controller: _name,
            textCapitalization: TextCapitalization.words,
            maxLength: maxNameLength,
            decoration: const InputDecoration(
              labelText: 'Name',
              border: OutlineInputBorder(),
              counterText: '',
            ),
            validator: (value) =>
                (value?.trim() ?? '').isEmpty ? 'Enter your name' : null,
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _dateOfBirthText,
            readOnly: true,
            onTap: _pickDateOfBirth,
            decoration: const InputDecoration(
              labelText: 'Date of birth',
              border: OutlineInputBorder(),
              suffixIcon: Icon(Icons.calendar_today_outlined),
            ),
            validator: (_) =>
                _dateOfBirth == null ? 'Choose your date of birth' : null,
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _cycleLength,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            decoration: const InputDecoration(
              labelText: 'Typical cycle length in days (optional)',
              helperText: 'From the first day of one period to the next',
              border: OutlineInputBorder(),
            ),
            validator: _optionalDays(minCycleLength, maxCycleLength),
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _periodLength,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            decoration: const InputDecoration(
              labelText: 'Typical period length in days (optional)',
              border: OutlineInputBorder(),
            ),
            validator: _optionalDays(minPeriodLength, maxPeriodLength),
          ),
          const SizedBox(height: 8),
          if (_settingUp)
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              value: _consented,
              onChanged: (value) => setState(() => _consented = value!),
              title: const Text(
                'I agree to Ova storing my health information, such as '
                'therapy sessions, cycle logs and chat messages, so the app '
                'can work.',
              ),
            )
          else
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _chatbotDataAccess,
              onChanged: (value) => setState(() => _chatbotDataAccess = value),
              title: const Text('Let the assistant use my data'),
              subtitle: const Text(
                'Allows the chat assistant to read your sessions and cycle '
                'logs.',
              ),
            ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: Text(widget.submitLabel),
          ),
        ],
      ),
    );
  }
}
