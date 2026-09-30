class ChatMessage {
  final String role; // "user" или "model"
  final String text;

  ChatMessage({required this.role, required this.text});

  Map<String, dynamic> toJson() => {'role': role, 'text': text};

  bool get isUser => role == 'user';
}
