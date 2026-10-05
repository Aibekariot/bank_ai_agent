import 'package:flutter/material.dart';
import '../models/message.dart';

class ChatBubble extends StatelessWidget {
  final ChatMessage message;

  const ChatBubble({super.key, required this.message});

  String _cleanMessage(String text) {
    return text.replaceAll('**', '');
  }

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    final cleanedText = _cleanMessage(message.text);

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        margin: const EdgeInsets.symmetric(
          vertical: 4,
          horizontal: 12,
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 10,
        ),
        decoration: BoxDecoration(
          color: isUser ? Colors.blue.shade600 : Colors.grey.shade200,
          borderRadius: BorderRadius.circular(16),
        ),
        child: SelectableText(
          cleanedText,
          style: TextStyle(
            color: isUser ? Colors.white : Colors.black87,
            fontSize: 15,
          ),
        ),
      ),
    );
  }
}