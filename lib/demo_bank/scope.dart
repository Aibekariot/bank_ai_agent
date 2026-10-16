import 'package:flutter/widgets.dart';

import 'data/demo_bank_api.dart';
import 'data/fake_bank_store.dart';

/// Сервисы демо-банка, доступные всем экранам. В тестах подменяются.
class DemoBankScope extends InheritedWidget {
  const DemoBankScope({
    super.key,
    required this.api,
    required this.store,
    required this.assistantBaseUrl,
    required super.child,
  });

  final DemoBankApi api;
  final FakeBankStore store;
  final String assistantBaseUrl;

  static DemoBankScope of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<DemoBankScope>();
    assert(scope != null, 'DemoBankScope не найден над этим виджетом');
    return scope!;
  }

  @override
  bool updateShouldNotify(DemoBankScope oldWidget) =>
      api != oldWidget.api ||
      store != oldWidget.store ||
      assistantBaseUrl != oldWidget.assistantBaseUrl;
}
