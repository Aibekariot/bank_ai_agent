// Проверка демо-банка с настоящим сервером. Запускается только по желанию:
//
//   cd backend && uvicorn main:app --port 8000
//   flutter test test/live_server_test.dart --dart-define=LIVE_API=http://127.0.0.1:8000
//
// Без LIVE_API тесты пропускаются (обычный `flutter test` их не запускает).
// Вопрос ассистенту тратит 2-3 запроса к модели и занимает до минуты.

import 'package:bank_ai_agent/demo_bank/data/demo_bank_api.dart';
import 'package:eldik_assistant/eldik_assistant.dart';
import 'package:flutter_test/flutter_test.dart';

const liveApi = String.fromEnvironment('LIVE_API');

void main() {
  final Object skip = liveApi.isEmpty ? 'нужен --dart-define=LIVE_API=<адрес сервера>' : false;

  test('данные демо-банка приходят с сервера', () async {
    final api = HttpDemoBankApi(liveApi);

    final places = await api.locations(query: 'Ош');
    expect(places, isNotEmpty);

    final cards = await api.cards();
    expect(cards.map((c) => c.slug), contains('visa-gold'));

    final card = await api.card('visa-gold');
    expect(card.name, 'Visa Gold');

    final rates = await api.rates();
    expect(rates.cash.map((r) => r.currency), contains('USD'));
  }, skip: skip);

  test('ассистент отвечает и предлагает кнопку курсов', () async {
    final api = AssistantApi(AssistantConfig(
      baseUrl: liveApi,
      authToken: 'demo-token-live-test',
      sessionId: 'live-test',
    ));
    final reply = await api.send([ChatMessage(role: 'user', text: 'какой курс доллара?')]);
    api.close();

    expect(reply.text, isNotEmpty);
    expect(reply.actions.map((a) => a.name), contains('open_exchange_rates'));
  }, skip: skip, timeout: const Timeout(Duration(minutes: 2)));
}
