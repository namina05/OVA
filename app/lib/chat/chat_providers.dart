import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../auth/auth_providers.dart';
import 'chat_service.dart';

final chatServiceProvider = Provider<ChatService>((ref) {
  final userId = ref.watch(
    currentUserProvider.select((user) => user.valueOrNull?.id),
  );
  if (userId == null) throw StateError('No one is signed in');
  return SupabaseChatService(Supabase.instance.client, userId: userId);
});
