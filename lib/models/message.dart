class ChatMessage {
  final String role; // "user" или "model"
  final String text;

  /// Сообщение об ошибке связи: показывается в чате, но не уходит на сервер.
  final bool isError;

  ChatMessage({required this.role, required this.text, this.isError = false});

  Map<String, dynamic> toJson() => {'role': role, 'text': text};

  bool get isUser => role == 'user';
}
