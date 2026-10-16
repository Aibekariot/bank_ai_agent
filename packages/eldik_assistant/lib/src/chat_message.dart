import 'assistant_action.dart';

/// Сообщение диалога.
class ChatMessage {
  ChatMessage({
    required this.role,
    required this.text,
    this.isError = false,
    this.actions = const [],
  });

  final String role; // "user" или "model"
  final String text;

  /// Сообщение об ошибке связи: показывается в чате, но не уходит на сервер.
  final bool isError;

  /// Действия, предложенные ассистентом под этим ответом.
  final List<AssistantAction> actions;

  Map<String, dynamic> toJson() => {'role': role, 'text': text};

  bool get isUser => role == 'user';
}
