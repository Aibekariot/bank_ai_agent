import 'package:eldik_assistant/eldik_assistant.dart';
import 'package:flutter/material.dart';

import '../screens/card_products_screen.dart';
import '../screens/exchange_rates_screen.dart';
import '../screens/locations_screen.dart';
import '../screens/pin_change_screen.dart';
import '../screens/transfer_screen.dart';

/// Выполняет действия ассистента в демо-банке. Каталог: contract/actions.json.
///
/// Приложение не доверяет серверу: неизвестное действие не показывается,
/// неверный параметр не подставляется, перевод клиент подтверждает сам.
class DemoActionHandler implements AssistantActionHandler {
  const DemoActionHandler();

  static const Set<String> supported = {
    'open_exchange_rates',
    'open_locations',
    'open_card_product',
    'open_pin_change',
    'open_transfer_by_phone',
  };

  static final RegExp _currency = RegExp(r'^[A-Z]{3}$');
  static final RegExp _slug = RegExp(r'^[A-Za-z0-9-]{1,80}$');
  static final RegExp _phone = RegExp(r'^\+996\d{9}$');

  @override
  Set<String> get supportedActions => supported;

  @override
  String labelFor(AssistantAction action) => action.label;

  @override
  Future<void> handle(BuildContext context, AssistantAction action) async {
    final screen = screenFor(action);
    if (screen == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Это действие пока недоступно')),
      );
      return;
    }
    await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => screen));
  }

  /// Экран для действия или null, если действие неизвестно или без
  /// обязательных параметров. Неверные необязательные параметры отбрасываются.
  static Widget? screenFor(AssistantAction action) {
    switch (action.name) {
      case 'open_exchange_rates':
        final currency = action.stringParam('currency');
        return ExchangeRatesScreen(
          currency: currency != null && _currency.hasMatch(currency) ? currency : null,
        );
      case 'open_locations':
        final city = action.stringParam('city');
        final kind = action.stringParam('kind');
        return LocationsScreen(
          city: city != null && city.length <= 60 ? city : null,
          kind: LocationsScreen.kinds.containsKey(kind) ? kind : null,
        );
      case 'open_card_product':
        final slug = action.stringParam('slug');
        if (slug == null || !_slug.hasMatch(slug)) return null;
        return CardProductScreen(slug: slug, title: action.stringParam('title'));
      case 'open_pin_change':
        return const PinChangeScreen();
      case 'open_transfer_by_phone':
        final phone = action.stringParam('phone');
        final amount = action.numberParam('amount');
        return TransferScreen(
          phone: phone != null && _phone.hasMatch(phone) ? phone : null,
          amount: amount != null && amount >= 1 ? amount : null,
          fromAssistant: true,
        );
    }
    return null;
  }
}
