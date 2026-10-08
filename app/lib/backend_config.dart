/// Where the Ova backend (cycle predictions and heat recommendations) runs.
///
/// The default is the phone's or emulator's own port 8000, which reaches a
/// backend on the development machine once that port is forwarded over USB:
/// `adb reverse tcp:8000 tcp:8000` (again after the device reconnects).
/// Point the app elsewhere with
/// `flutter run --dart-define=OVA_BACKEND_URL=https://example.com`.
const backendUrl = String.fromEnvironment(
  'OVA_BACKEND_URL',
  defaultValue: 'http://127.0.0.1:8000',
);
