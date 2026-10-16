import 'dart:convert';

import 'package:eldik_assistant/eldik_assistant.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response jsonResponse(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

void main() {
  const config = AssistantConfig(
    baseUrl: 'http://test',
    authToken: 'demo-token',
    sessionId: 's1',
  );

  test('отправляет историю без ошибок связи, токен и session_id', () async {
    late http.Request sent;
    final api = AssistantApi(config, client: MockClient((request) async {
      sent = request;
      return jsonResponse({'reply': 'ok', 'actions': []});
    }));

    await api.send([
      ChatMessage(role: 'user', text: 'курс доллара'),
      ChatMessage(role: 'model', text: 'нет связи', isError: true),
      ChatMessage(role: 'user', text: 'ещё раз'),
    ]);

    expect(sent.url.toString(), 'http://test/v1/chat');
    expect(sent.headers['Authorization'], 'Bearer demo-token');
    final body = jsonDecode(sent.body) as Map<String, dynamic>;
    expect(body['session_id'], 's1');
    expect(body['messages'], [
      {'role': 'user', 'text': 'курс доллара'},
      {'role': 'user', 'text': 'ещё раз'},
    ]);
  });

  test('разбирает ответ и действия, неверные действия пропускает', () async {
    final api = AssistantApi(config, client: MockClient((_) async => jsonResponse({
          'reply': 'Курс доллара: 87,30',
          'actions': [
            {'name': 'open_exchange_rates', 'label': 'Курсы валют: USD', 'params': {'currency': 'USD'}},
            {'label': 'без имени'},
            'не объект',
            {'name': 'open_pin_change'},
          ],
        })));

    final reply = await api.send([ChatMessage(role: 'user', text: 'курс')]);

    expect(reply.text, 'Курс доллара: 87,30');
    expect(reply.actions.map((a) => a.name), ['open_exchange_rates', 'open_pin_change']);
    expect(reply.actions.first.stringParam('currency'), 'USD');
    expect(reply.actions.last.label, 'open_pin_change'); // нет подписи - имя
  });

  test('ответ без поля actions - пустой список', () async {
    final api = AssistantApi(config, client: MockClient((_) async => jsonResponse({'reply': 'Привет'})));
    final reply = await api.send([ChatMessage(role: 'user', text: 'привет')]);
    expect(reply.actions, isEmpty);
  });

  test('ошибка сервера: текст из detail', () async {
    final api = AssistantApi(config, client: MockClient((_) async =>
        jsonResponse({'detail': 'Сервис сейчас перегружен.'}, 503)));
    expect(
      () => api.send([ChatMessage(role: 'user', text: 'x')]),
      throwsA(isA<ApiException>().having((e) => e.message, 'message', 'Сервис сейчас перегружен.')),
    );
  });

  test('ошибка сервера без detail: общий текст', () async {
    final api = AssistantApi(config, client: MockClient((_) async => http.Response('oops', 500)));
    expect(
      () => api.send([ChatMessage(role: 'user', text: 'x')]),
      throwsA(isA<ApiException>().having((e) => e.message, 'message', 'Ошибка сервера (500).')),
    );
  });

  test('долгий ответ: понятная ошибка таймаута', () async {
    final api = AssistantApi(
      const AssistantConfig(baseUrl: 'http://test', timeout: Duration(milliseconds: 50)),
      client: MockClient((_) async {
        await Future<void>.delayed(const Duration(milliseconds: 300));
        return jsonResponse({'reply': 'поздно'});
      }),
    );
    expect(
      () => api.send([ChatMessage(role: 'user', text: 'x')]),
      throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('долго не отвечает'))),
    );
  });
}
