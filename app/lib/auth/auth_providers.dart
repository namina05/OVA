import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'auth_service.dart';

final authServiceProvider = Provider<AuthService>((ref) {
  return SupabaseAuthService(Supabase.instance.client.auth);
});

final currentUserProvider = StreamProvider<AppUser?>((ref) {
  return ref.watch(authServiceProvider).userChanges;
});
