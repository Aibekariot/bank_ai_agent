import 'dart:convert';

import 'package:eldik_assistant/eldik_assistant.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Обработчик-заглушка: запоминает выполненные действия.
class RecordingHandler implements AssistantActionHandler {
  final List<AssistantAction> handled = [];

  @override
  Set<String> get supportedActions => {'open_exchange_rates'};

  @override
  String labelFor(AssistantAction action) => 'Открыть: ${action.label}';

  @override
  Future<void> handle(BuildContext context, AssistantAction action) async {
    handled.add(action);
  }
}

void main() {
  const config = AssistantConfig(baseUrl: 'http://test');

  Future<AssistantApi> pumpChat(WidgetTester tester, AssistantActionHandler? handler) async {
    final api = AssistantApi(config, client: MockClient((request) async {
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      // Приветствие не уходит на сервер: первое сообщение - вопрос клиента.
      expect((body['messages'] as List).first['role'], 'user');
      return http.Response.bytes(
        utf8.encode(jsonEncode({
          'reply': 'Курс доллара: 87,30 / 87,80.',
          'actions': [
            {'name': 'open_exchange_rates', 'label': 'Курсы валют: USD', 'params': {'currency': 'USD'}},
            {'name': 'make_payment', 'label': 'Оплатить всё', 'params': {}},
          ],
        })),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }));
    await tester.pumpWidget(MaterialApp(
      home: AssistantChatScreen(config: config, actionHandler: handler, api: api),
    ));
    await tester.enterText(find.byType(TextField), 'какой курс доллара?');
    await tester.tap(find.byTooltip('Отправить'));
    await tester.pumpAndSettle();
    return api;
  }

  testWidgets('показывает кнопку только для поддерживаемого действия', (tester) async {
    final handler = RecordingHandler();
    await pumpChat(tester, handler);

    expect(find.textContaining('Курс доллара: 87,30'), findsOneWidget);
    expect(find.text('Открыть: Курсы валют: USD'), findsOneWidget);
    expect(find.textContaining('Оплатить всё'), findsNothing);

    await tester.tap(find.text('Открыть: Курсы валют: USD'));
    await tester.pump();
    expect(handler.handled.single.stringParam('currency'), 'USD');
  });

  testWidgets('без обработчика кнопок нет', (tester) async {
    await pumpChat(tester, null);
    expect(find.textContaining('Курс доллара: 87,30'), findsOneWidget);
    expect(find.byType(OutlinedButton), findsNothing);
  });
}
