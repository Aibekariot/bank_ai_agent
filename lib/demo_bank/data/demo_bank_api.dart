import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// Курс одной валюты.
class ExchangeRate {
  const ExchangeRate({required this.currency, required this.buy, required this.sell});

  final String currency;
  final num buy;
  final num sell;
}

class RatesData {
  const RatesData({
    required this.date,
    required this.note,
    required this.cash,
    required this.cashless,
  });

  final String date;
  final String note;
  final List<ExchangeRate> cash;
  final List<ExchangeRate> cashless;
}

/// Банкомат, филиал или касса.
class BankLocation {
  const BankLocation({
    required this.type,
    required this.name,
    required this.address,
    this.phones = const [],
    this.mapLink,
  });

  final String type;
  final String name;
  final String address;
  final List<String> phones;
  final String? mapLink;
}

/// Карта в списке продуктов банка.
class CardProductSummary {
  const CardProductSummary({
    required this.slug,
    required this.name,
    this.category,
    this.issuance,
    this.annualService,
  });

  final String slug;
  final String name;
  final String? category;
  final String? issuance;
  final String? annualService;
}

/// Страница карты. null в стоимости значит "не указано", а не "бесплатно".
class CardProduct {
  const CardProduct({
    required this.slug,
    required this.name,
    this.category,
    this.paymentSystem,
    this.currencies = const [],
    this.issuance,
    this.annualService,
    this.expiration,
    this.details = '',
    this.partialData = false,
    this.dataDate,
  });

  final String slug;
  final String name;
  final String? category;
  final String? paymentSystem;
  final List<String> currencies;
  final String? issuance;
  final String? annualService;
  final String? expiration;
  final String details;
  final bool partialData;
  final String? dataDate;
}

/// Ошибка загрузки с текстом для пользователя.
class DemoBankApiException implements Exception {
  DemoBankApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Текст ошибки для экрана.
String describeError(Object? error) => error is DemoBankApiException
    ? error.message
    : 'Не удалось загрузить данные. Проверьте связь с сервером.';

/// Данные банка для экранов демо-приложения.
///
/// Настоящее приложение берёт их из систем банка; здесь их отдаёт
/// имитация API банка на сервере ассистента (/demo-bank/v1).
abstract interface class DemoBankApi {
  Future<RatesData> rates();
  Future<List<BankLocation>> locations({String query = '', String kind = ''});
  Future<List<CardProductSummary>> cards();
  Future<CardProduct> card(String slug);
}

class HttpDemoBankApi implements DemoBankApi {
  HttpDemoBankApi(this.baseUrl, {http.Client? client})
      : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Future<Object?> _get(String path, [Map<String, String> query = const {}]) async {
    var uri = Uri.parse('$baseUrl/demo-bank/v1$path');
    if (query.isNotEmpty) uri = uri.replace(queryParameters: query);

    final http.Response response;
    try {
      response = await _client.get(uri).timeout(const Duration(seconds: 20));
    } on TimeoutException {
      throw DemoBankApiException('Сервер долго не отвечает. Попробуйте ещё раз.');
    } catch (_) {
      throw DemoBankApiException('Нет связи с сервером. Проверьте адрес и сеть.');
    }

    if (response.statusCode != 200) {
      String? detail;
      try {
        final body = jsonDecode(utf8.decode(response.bodyBytes));
        if (body is Map && body['detail'] is String) detail = body['detail'] as String;
      } on FormatException {
        // Не JSON: покажем общее сообщение.
      }
      throw DemoBankApiException(detail ?? 'Ошибка сервера (${response.statusCode}).');
    }
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  static String? _text(Object? value) =>
      value is String && value.isNotEmpty ? value : null;

  static List<Map<String, Object?>> _items(Object? list) => list is List
      ? list.whereType<Map<String, Object?>>().toList()
      : const [];

  static List<ExchangeRate> _rates(Object? list) => [
        for (final r in _items(list))
          if (r['currency'] is String && r['buy'] is num && r['sell'] is num)
            ExchangeRate(
              currency: r['currency'] as String,
              buy: r['buy'] as num,
              sell: r['sell'] as num,
            ),
      ];

  @override
  Future<RatesData> rates() async {
    final data = await _get('/rates');
    if (data is! Map) throw DemoBankApiException('Сервер вернул неожиданный ответ.');
    return RatesData(
      date: _text(data['date']) ?? 'дата не указана',
      note: _text(data['note']) ?? '',
      cash: _rates(data['cash']),
      cashless: _rates(data['cashless']),
    );
  }

  @override
  Future<List<BankLocation>> locations({String query = '', String kind = ''}) async {
    final data = await _get('/locations', {
      if (query.isNotEmpty) 'query': query,
      if (kind.isNotEmpty) 'kind': kind,
    });
    if (data is! Map) throw DemoBankApiException('Сервер вернул неожиданный ответ.');
    return [
      for (final item in _items(data['items']))
        BankLocation(
          type: _text(item['type']) ?? 'Точка обслуживания',
          name: _text(item['name']) ?? 'Без названия',
          address: _text(item['address']) ?? 'адрес не указан',
          phones: [
            for (final p in (item['phones'] is List ? item['phones'] as List : const []))
              if (p is String && p.trim().isNotEmpty && p.trim() != '-') p,
          ],
          mapLink: _text(item['map_link']),
        ),
    ];
  }

  @override
  Future<List<CardProductSummary>> cards() async {
    final data = await _get('/cards');
    if (data is! Map) throw DemoBankApiException('Сервер вернул неожиданный ответ.');
    return [
      for (final item in _items(data['items']))
        if (_text(item['slug']) != null)
          CardProductSummary(
            slug: item['slug'] as String,
            name: _text(item['name']) ?? item['slug'] as String,
            category: _text(item['category']),
            issuance: _text(item['issuance']),
            annualService: _text(item['annual_service']),
          ),
    ];
  }

  @override
  Future<CardProduct> card(String slug) async {
    final data = await _get('/cards/${Uri.encodeComponent(slug)}');
    if (data is! Map) throw DemoBankApiException('Сервер вернул неожиданный ответ.');
    return CardProduct(
      slug: slug,
      name: _text(data['name']) ?? slug,
      category: _text(data['category']),
      paymentSystem: _text(data['payment_system']),
      currencies: [
        for (final c in (data['currencies'] is List ? data['currencies'] as List : const []))
          if (c is String) c,
      ],
      issuance: _text(data['issuance']),
      annualService: _text(data['annual_service']),
      expiration: _text(data['card_expiration_date']),
      details: _text(data['details']) ?? '',
      partialData: data['partial_data'] == true,
      dataDate: _text(data['data_date']),
    );
  }
}
