import 'package:flutter/material.dart';
import 'screens/chat_screen.dart';

void main() {
  runApp(const EldikBankApp());
}
class EldikBankApp extends StatelessWidget {
  const EldikBankApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Eldik Bank AI Agent',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        primarySwatch: Colors.blue,
        useMaterial3: true,
      ),
      home: const ChatScreen(),
    );
  }
}
