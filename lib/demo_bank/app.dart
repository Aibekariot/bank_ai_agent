import 'package:flutter/material.dart';

import 'config.dart';
import 'data/demo_bank_api.dart';
import 'data/fake_bank_store.dart';
import 'scope.dart';
import 'screens/login_screen.dart';

/// Демо-банк: тестовое приложение-хозяин для ИИ-ассистента.
///
/// Нужен, чтобы проверять действия ассистента (кнопки, переход на экраны,
/// подтверждение перевода) до интеграции с настоящим приложением банка.
/// Все данные клиента вымышленные.
class DemoBankApp extends StatelessWidget {
  const DemoBankApp({
    super.key,
    required this.api,
    required this.store,
    required this.assistantBaseUrl,
  });

  factory DemoBankApp.create() => DemoBankApp(
        api: HttpDemoBankApi(apiBaseUrl),
        store: FakeBankStore(),
        assistantBaseUrl: apiBaseUrl,
      );

  final DemoBankApi api;
  final FakeBankStore store;
  final String assistantBaseUrl;

  @override
  Widget build(BuildContext context) {
    return DemoBankScope(
      api: api,
      store: store,
      assistantBaseUrl: assistantBaseUrl,
      child: MaterialApp(
        title: 'Демо-банк',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
        home: const LoginScreen(),
      ),
    );
  }
}
