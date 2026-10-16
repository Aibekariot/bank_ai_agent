import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'assistant_action.dart';
import 'assistant_config.dart';
import 'chat_message.dart';

/// Ошибка с текстом, который можно показать пользователю.
class ApiException implements Exception {
  ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Ответ ассистента: текст и предложенные действия.
class AssistantReply {
  const AssistantReply({required this.text, this.actions = const []});

  final String text;
  final List<AssistantAction> actions;
}

/// Клиент сервера ассистента. Контракт: contract/README.md.
class AssistantApi {
  AssistantApi(this.config, {http.Client? client})
      : _client = client ?? http.Client(),
        _ownsClient = client == null;

  final AssistantConfig config;
  final http.Client _client;
  final bool _ownsClient;

  Future<AssistantReply> send(List<ChatMessage> history) async {
    final http.Response response;
    try {
      response = await _client
          .post(
            Uri.parse('${config.baseUrl}/v1/chat'),
            headers: {
              'Content-Type': 'application/json',
              if (config.authToken != null)
                'Authorization': 'Bearer ${config.authToken}',
            },
            body: jsonEncode({
              // Сообщения об ошибках связи модели не отправляем.
              'messages': history
                  .where((m) => !m.isError)
                  .map((m) => m.toJson())
                  .toList(),
              if (config.sessionId != null) 'session_id': config.sessionId,
            }),
          )
          .timeout(config.timeout);
    } on TimeoutException {
      throw ApiException('Ассистент долго не отвечает. Попробуйте ещё раз.');
    }

    if (response.statusCode != 200) {
      // Сервер отдаёт короткое безопасное сообщение в поле detail.
      String? detail;
      try {
        final body = jsonDecode(utf8.decode(response.bodyBytes));
        if (body is Map && body['detail'] is String) {
          detail = body['detail'] as String;
        }
      } on FormatException {
        // Не JSON: покажем общее сообщение.
      }
      throw ApiException(detail ?? 'Ошибка сервера (${response.statusCode}).');
    }

    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is! Map || decoded['reply'] is! String) {
      throw ApiException('Сервер вернул неожиданный ответ.');
    }

    // Действие, которое не удалось разобрать, просто не показываем.
    final rawActions = decoded['actions'];
    final actions = rawActions is List
        ? rawActions
            .map(AssistantAction.tryParse)
            .whereType<AssistantAction>()
            .toList()
        : <AssistantAction>[];

    return AssistantReply(text: decoded['reply'] as String, actions: actions);
  }

  /// Закрывает HTTP-клиент, если он создан здесь.
  void close() {
    if (_ownsClient) _client.close();
  }
}
