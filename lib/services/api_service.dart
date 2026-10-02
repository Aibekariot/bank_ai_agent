import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/message.dart';

class ApiService {
  // При запуске на эмуляторе Android localhost бэкенда - это 10.0.2.2,
  // не 127.0.0.1. Для iOS-симулятора и веба подходит 127.0.0.1.
  // При деплое backend куда-то - заменить на реальный URL.
  static const String baseUrl = 'http://10.208.18.28:8000';

  Future<String> sendMessage(List<ChatMessage> history) async {
    final response = await http.post(
      Uri.parse('$baseUrl/chat'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'messages': history.map((m) => m.toJson()).toList(),
      }),
    );

    if (response.statusCode != 200) {
      throw Exception('Ошибка сервера: ${response.statusCode} ${response.body}');
    }

    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    return decoded['reply'] as String;
  }
}
