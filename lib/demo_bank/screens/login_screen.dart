import 'package:flutter/material.dart';

import '../data/fake_bank_store.dart';
import '../scope.dart';
import '../widgets/demo_widgets.dart';
import 'home_screen.dart';

/// Вход тестового клиента. Нужен, чтобы токен и session_id были в контракте
/// с ассистентом с первого дня; настоящей проверки здесь нет.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final TextEditingController _pin = TextEditingController();
  String? _error;

  void _login() {
    final store = DemoBankScope.of(context).store;
    if (!store.login(_pin.text)) {
      setState(() => _error = 'Неверный PIN-код');
      return;
    }
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const HomeScreen()),
    );
  }

  @override
  void dispose() {
    _pin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: demoAppBar('Демо-банк'),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text('Вход', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 12),
          const InfoBanner(
            text: 'Демо-приложение для проверки ИИ-ассистента. Все счета, '
                'карты и операции вымышленные.',
          ),
          const SizedBox(height: 20),
          TextFormField(
            initialValue: FakeBankStore.demoPhone,
            readOnly: true,
            decoration: const InputDecoration(
              labelText: 'Телефон',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _pin,
            obscureText: true,
            keyboardType: TextInputType.number,
            maxLength: 4,
            onSubmitted: (_) => _login(),
            decoration: InputDecoration(
              labelText: 'PIN-код',
              helperText: 'Демо: PIN ${FakeBankStore.demoPin}',
              errorText: _error,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton(onPressed: _login, child: const Text('Войти')),
        ],
      ),
    );
  }
}
