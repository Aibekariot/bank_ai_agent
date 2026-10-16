import 'dart:convert';
import 'dart:io';

import 'package:bank_ai_agent/demo_bank/actions/demo_action_handler.dart';
import 'package:bank_ai_agent/demo_bank/screens/card_products_screen.dart';
import 'package:bank_ai_agent/demo_bank/screens/exchange_rates_screen.dart';
import 'package:bank_ai_agent/demo_bank/screens/locations_screen.dart';
import 'package:bank_ai_agent/demo_bank/screens/pin_change_screen.dart';
import 'package:bank_ai_agent/demo_bank/screens/transfer_screen.dart';
import 'package:eldik_assistant/eldik_assistant.dart';
import 'package:flutter_test/flutter_test.dart';

/// Каталог действий, общий с сервером (contract/actions.json).
Map<String, dynamic> loadCatalog() {
  final file = File('contract/actions.json');
  final data = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
  return data['actions'] as Map<String, dynamic>;
}

AssistantAction action(String name, [Map<String, Object?> params = const {}]) =>
    AssistantAction(name: name, label: name, params: params);

void main() {
  final catalog = loadCatalog();

  test('приложение поддерживает ровно действия из каталога', () {
    expect(DemoActionHandler.supported, catalog.keys.toSet());
  });

  test('пример каждого действия из каталога открывает экран', () {
    for (final entry in catalog.entries) {
      final example = Map<String, Object?>.from(entry.value['example'] as Map);
      expect(DemoActionHandler.screenFor(action(entry.key, example)), isNotNull,
          reason: entry.key);
    }
  });

  test('параметры доходят до экранов', () {
    final rates = DemoActionHandler.screenFor(action('open_exchange_rates', {'currency': 'USD'}));
    expect((rates as ExchangeRatesScreen).currency, 'USD');

    final places = DemoActionHandler.screenFor(action('open_locations', {'city': 'Ош', 'kind': 'branch'}));
    expect((places as LocationsScreen).city, 'Ош');
    expect(places.kind, 'branch');

    final card = DemoActionHandler.screenFor(action('open_card_product', {'slug': 'visa-gold', 'title': 'Visa Gold'}));
    expect((card as CardProductScreen).slug, 'visa-gold');

    expect(DemoActionHandler.screenFor(action('open_pin_change')), isA<PinChangeScreen>());

    final transfer = DemoActionHandler.screenFor(
        action('open_transfer_by_phone', {'phone': '+996555123456', 'amount': 500, 'currency': 'KGS'}));
    expect((transfer as TransferScreen).phone, '+996555123456');
    expect(transfer.amount, 500);
    expect(transfer.fromAssistant, isTrue);
  });

  test('приложение не доверяет серверу: неверные параметры не подставляются', () {
    expect(DemoActionHandler.screenFor(action('make_payment', {'amount': 1000000})), isNull);
    expect(DemoActionHandler.screenFor(action('open_card_product')), isNull,
        reason: 'нет обязательного slug');
    expect(DemoActionHandler.screenFor(action('open_card_product', {'slug': '../etc/passwd'})), isNull);

    final rates = DemoActionHandler.screenFor(action('open_exchange_rates', {'currency': 'usd; drop'}));
    expect((rates as ExchangeRatesScreen).currency, isNull);

    final places = DemoActionHandler.screenFor(action('open_locations', {'kind': 'teleport'}));
    expect((places as LocationsScreen).kind, isNull);

    final transfer = DemoActionHandler.screenFor(
        action('open_transfer_by_phone', {'phone': '0555123456', 'amount': -5}));
    expect((transfer as TransferScreen).phone, isNull);
    expect(transfer.amount, isNull);
  });
}
