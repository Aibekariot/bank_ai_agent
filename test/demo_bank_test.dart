import 'package:bank_ai_agent/demo_bank/actions/demo_action_handler.dart';
import 'package:bank_ai_agent/demo_bank/data/fake_bank_store.dart';
import 'package:bank_ai_agent/demo_bank/format.dart';
import 'package:bank_ai_agent/demo_bank/screens/card_products_screen.dart';
import 'package:bank_ai_agent/demo_bank/screens/exchange_rates_screen.dart';
import 'package:bank_ai_agent/demo_bank/screens/home_screen.dart';
import 'package:bank_ai_agent/demo_bank/screens/login_screen.dart';
import 'package:bank_ai_agent/demo_bank/screens/pin_change_screen.dart';
import 'package:bank_ai_agent/demo_bank/screens/transfer_screen.dart';
import 'package:eldik_assistant/eldik_assistant.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_demo_bank_api.dart';

void main() {
  group('форматирование', () {
    test('суммы', () {
      expect(formatMoney(25000, 'KGS'), '25 000 KGS');
      expect(formatMoney(1500.5, 'KGS'), '1 500,50 KGS');
      expect(formatMoney(300, 'USD'), '300 USD');
    });

    test('номер телефона: те же правила, что на сервере', () {
      expect(normalizeKgPhone('0555 123 456'), '+996555123456');
      expect(normalizeKgPhone('+996 (555) 12-34-56'), '+996555123456');
      expect(normalizeKgPhone('555123456'), '+996555123456');
      expect(normalizeKgPhone('12345'), isNull);
      expect(formatPhone('+996555123456'), '+996 555 123 456');
    });
  });

  testWidgets('вход: неверный PIN, затем верный открывает главный экран', (tester) async {
    final store = FakeBankStore();
    await tester.pumpWidget(testApp(home: const LoginScreen(), store: store));
    final pinField = find.byType(TextField).last; // первое поле - телефон

    await tester.enterText(pinField, '0000');
    await tester.tap(find.text('Войти'));
    await tester.pump();
    expect(find.text('Неверный PIN-код'), findsOneWidget);

    await tester.enterText(pinField, FakeBankStore.demoPin);
    await tester.tap(find.text('Войти'));
    await tester.pumpAndSettle();
    expect(find.byType(HomeScreen), findsOneWidget);
    expect(store.token, isNotNull);
  });

  testWidgets('перевод от ассистента: форма заполнена, без PIN денег не списывает', (tester) async {
    final store = FakeBankStore();
    await tester.pumpWidget(testApp(
      store: store,
      home: const TransferScreen(phone: '+996555123456', amount: 500, fromAssistant: true),
    ));

    expect(find.textContaining('Данные заполнены ассистентом'), findsOneWidget);
    expect(find.text('+996 555 123 456'), findsOneWidget);
    expect(find.text('500'), findsOneWidget);
    expect(store.kgsAccount.balance, 25000, reason: 'открытие формы ничего не списывает');

    await tester.tap(find.text('Продолжить'));
    await tester.pumpAndSettle();
    expect(find.text('Проверьте перевод'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '0000');
    await tester.tap(find.text('Подтвердить перевод'));
    await tester.pump();
    expect(find.text('Неверный PIN-код'), findsOneWidget);
    expect(store.kgsAccount.balance, 25000, reason: 'неверный PIN не проводит перевод');

    await tester.enterText(find.byType(TextField), FakeBankStore.demoPin);
    await tester.tap(find.text('Подтвердить перевод'));
    await tester.pumpAndSettle();
    expect(find.text('Перевод выполнен'), findsOneWidget);
    expect(store.kgsAccount.balance, 24500);
    expect(store.transfers.single.phone, '+996555123456');
  });

  testWidgets('перевод: неверный номер и сумма больше баланса не проходят', (tester) async {
    final store = FakeBankStore();
    await tester.pumpWidget(testApp(store: store, home: const TransferScreen()));

    await tester.enterText(find.byType(TextField).at(0), '12345');
    await tester.enterText(find.byType(TextField).at(1), '100');
    await tester.tap(find.text('Продолжить'));
    await tester.pump();
    expect(find.textContaining('Введите номер мобильного телефона'), findsOneWidget);

    await tester.enterText(find.byType(TextField).at(0), '0555 123 456');
    await tester.enterText(find.byType(TextField).at(1), '1000000');
    await tester.tap(find.text('Продолжить'));
    await tester.pump();
    expect(find.text('Недостаточно средств на счёте'), findsOneWidget);
    expect(find.text('Проверьте перевод'), findsNothing);
  });

  testWidgets('смена PIN: проверка совпадения и успешный итог', (tester) async {
    await tester.pumpWidget(testApp(home: const PinChangeScreen(cardId: 'visa-gold')));

    await tester.enterText(find.byType(TextField).at(0), '4321');
    await tester.enterText(find.byType(TextField).at(1), '4320');
    await tester.tap(find.text('Сменить PIN-код'));
    await tester.pump();
    expect(find.text('PIN-коды не совпадают'), findsOneWidget);

    await tester.enterText(find.byType(TextField).at(1), '4321');
    await tester.tap(find.text('Сменить PIN-код'));
    await tester.pump();
    expect(find.text('PIN-код изменён'), findsOneWidget);
  });

  testWidgets('страница карты: «не указано» вместо «бесплатно» для пустого поля', (tester) async {
    await tester.pumpWidget(testApp(home: const CardProductScreen(slug: 'visa-gold', title: 'Visa Gold')));
    await tester.pumpAndSettle();
    expect(find.text('Бесплатно'), findsOneWidget); // выпуск указан
    expect(find.text('не указано'), findsNWidgets(2)); // обслуживание и срок не указаны
  });

  testWidgets('кнопка ассистента открывает экран курсов с выделенной валютой', (tester) async {
    const handler = DemoActionHandler();
    await tester.pumpWidget(testApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () => handler.handle(
              context,
              const AssistantAction(
                name: 'open_exchange_rates',
                label: 'Курсы валют: USD',
                params: {'currency': 'USD'},
              ),
            ),
            child: const Text('нажать'),
          ),
        ),
      ),
    ));

    await tester.tap(find.text('нажать'));
    await tester.pumpAndSettle();
    expect(find.byType(ExchangeRatesScreen), findsOneWidget);
    expect(find.text('Курсы на 2026-10-16'), findsOneWidget);
    expect(find.text('87,30'), findsNWidgets(1));
  });

  testWidgets('неизвестное действие: сообщение, экран не меняется', (tester) async {
    const handler = DemoActionHandler();
    await tester.pumpWidget(testApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () => handler.handle(
              context,
              const AssistantAction(name: 'make_payment', label: 'Оплатить'),
            ),
            child: const Text('нажать'),
          ),
        ),
      ),
    ));

    await tester.tap(find.text('нажать'));
    await tester.pump();
    expect(find.text('Это действие пока недоступно'), findsOneWidget);
    expect(find.text('нажать'), findsOneWidget);
  });
}
