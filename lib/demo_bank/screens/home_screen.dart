import 'package:eldik_assistant/eldik_assistant.dart';
import 'package:flutter/material.dart';

import '../actions/demo_action_handler.dart';
import '../format.dart';
import '../scope.dart';
import '../widgets/demo_widgets.dart';
import 'card_products_screen.dart';
import 'exchange_rates_screen.dart';
import 'locations_screen.dart';
import 'login_screen.dart';
import 'pin_change_screen.dart';
import 'transfer_screen.dart';

/// Главный экран: счета, карты, разделы и кнопка ассистента.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  void _open(BuildContext context, Widget screen) {
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => screen));
  }

  void _openAssistant(BuildContext context) {
    final scope = DemoBankScope.of(context);
    _open(
      context,
      AssistantChatScreen(
        config: AssistantConfig(
          baseUrl: scope.assistantBaseUrl,
          authToken: scope.store.token,
          sessionId: 'demo-${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}',
        ),
        actionHandler: const DemoActionHandler(),
      ),
    );
  }

  void _logout(BuildContext context) {
    DemoBankScope.of(context).store.logout();
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const LoginScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final store = DemoBankScope.of(context).store;

    return Scaffold(
      appBar: demoAppBar(
        'Демо-банк',
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Выйти',
            onPressed: () => _logout(context),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        icon: const Icon(Icons.support_agent),
        label: const Text('Ассистент'),
        onPressed: () => _openAssistant(context),
      ),
      body: ListenableBuilder(
        listenable: store,
        builder: (context, _) => ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
          children: [
            Text(
              'Здравствуйте, ${store.clientName}',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SectionTitle('Счета'),
            for (final account in store.accounts)
              Card(
                child: ListTile(
                  leading: const Icon(Icons.account_balance_wallet_outlined),
                  title: Text(account.title),
                  trailing: Text(
                    formatMoney(account.balance, account.currency),
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            const SectionTitle('Карты'),
            for (final card in store.cards)
              Card(
                child: ListTile(
                  leading: const Icon(Icons.credit_card),
                  title: Text(card.title),
                  subtitle: Text(card.maskedNumber),
                  trailing: TextButton(
                    onPressed: () => _open(context, PinChangeScreen(cardId: card.id)),
                    child: const Text('Сменить PIN'),
                  ),
                ),
              ),
            const SectionTitle('Разделы'),
            Card(
              child: Column(
                children: [
                  _Entry(Icons.send_to_mobile, 'Перевод по номеру телефона',
                      () => _open(context, const TransferScreen())),
                  _Entry(Icons.currency_exchange, 'Курсы валют',
                      () => _open(context, const ExchangeRatesScreen())),
                  _Entry(Icons.place_outlined, 'Банкоматы и отделения',
                      () => _open(context, const LocationsScreen())),
                  _Entry(Icons.credit_card_outlined, 'Карты банка',
                      () => _open(context, const CardProductsScreen())),
                  _Entry(Icons.pin_outlined, 'Смена PIN-кода',
                      () => _open(context, const PinChangeScreen())),
                ],
              ),
            ),
            if (store.transfers.isNotEmpty) ...[
              const SectionTitle('Последние переводы'),
              for (final t in store.transfers)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.north_east),
                    title: Text(formatPhone(t.phone)),
                    trailing: Text('-${formatMoney(t.amount, 'KGS')}'),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Entry extends StatelessWidget {
  const _Entry(this.icon, this.title, this.onTap);

  final IconData icon;
  final String title;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListTile(
        leading: Icon(icon),
        title: Text(title),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      );
}
