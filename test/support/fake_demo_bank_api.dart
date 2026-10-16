import 'package:bank_ai_agent/demo_bank/data/demo_bank_api.dart';
import 'package:bank_ai_agent/demo_bank/data/fake_bank_store.dart';
import 'package:bank_ai_agent/demo_bank/scope.dart';
import 'package:flutter/material.dart';

/// Данные банка без сервера: для тестов экранов.
class FakeDemoBankApi implements DemoBankApi {
  final List<String> locationQueries = [];

  @override
  Future<RatesData> rates() async => const RatesData(
        date: '2026-10-16',
        note: 'Курсы для головного отделения.',
        cash: [
          ExchangeRate(currency: 'USD', buy: 87.3, sell: 87.8),
          ExchangeRate(currency: 'EUR', buy: 101.2, sell: 102.9),
        ],
        cashless: [ExchangeRate(currency: 'USD', buy: 87.0, sell: 87.5)],
      );

  @override
  Future<List<BankLocation>> locations({String query = '', String kind = ''}) async {
    locationQueries.add('$query|$kind');
    return const [
      BankLocation(type: 'Филиал / отделение', name: 'Ош филиал', address: 'г. Ош, ул. Курманжан Датка, 124а'),
    ];
  }

  @override
  Future<List<CardProductSummary>> cards() async => const [
        CardProductSummary(slug: 'visa-gold', name: 'Visa Gold', category: 'Дебетовые карты'),
      ];

  @override
  Future<CardProduct> card(String slug) async => CardProduct(
        slug: slug,
        name: 'Visa Gold',
        issuance: 'Бесплатно',
        annualService: null, // не указано
        details: 'Условия карты.',
      );
}

/// Приложение с подменёнными сервисами и заданным первым экраном.
Widget testApp({
  required Widget home,
  FakeBankStore? store,
  DemoBankApi? api,
}) =>
    DemoBankScope(
      api: api ?? FakeDemoBankApi(),
      store: store ?? FakeBankStore(),
      assistantBaseUrl: 'http://test',
      child: MaterialApp(home: home),
    );
