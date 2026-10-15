import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/message.dart';

/// Ошибка с текстом, который можно показать пользователю.
class ApiException implements Exception {
  final String message;

  ApiException(this.message);

  @override
  String toString() => message;
}

class ApiService {
  // При запуске на эмуляторе Android localhost бэкенда - это 10.0.2.2,
  // не 127.0.0.1. Для iOS-симулятора и веба подходит 127.0.0.1.
  // При деплое backend куда-то - заменить на реальный URL.
  static const String baseUrl = 'http://10.179.11.28:8000';

  // Бесплатная модель отвечает до 25-30 секунд, берём с запасом.
  static const Duration timeout = Duration(seconds: 90);

  Future<String> sendMessage(List<ChatMessage> history) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/chat'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            // Сообщения об ошибках связи модели не отправляем.
            'messages': history
                .where((m) => !m.isError)
                .map((m) => m.toJson())
                .toList(),
          }),
        )
        .timeout(timeout);

    if (response.statusCode != 200) {
      // Сервер отдаёт короткое безопасное сообщение в поле detail.
      String? detail;
      try {
        detail = jsonDecode(utf8.decode(response.bodyBytes))['detail'] as String?;
      } catch (_) {}
      throw ApiException(detail ?? 'Ошибка сервера (${response.statusCode}).');
    }

    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    return decoded['reply'] as String;
  }
}
