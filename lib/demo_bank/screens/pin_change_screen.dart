import 'package:flutter/material.dart';

import '../scope.dart';
import '../widgets/demo_widgets.dart';

/// Смена PIN-кода карты (в демо PIN по-настоящему не меняется).
class PinChangeScreen extends StatefulWidget {
  const PinChangeScreen({super.key, this.cardId});

  /// Карта, выбранная заранее (например, с главного экрана).
  final String? cardId;

  @override
  State<PinChangeScreen> createState() => _PinChangeScreenState();
}

class _PinChangeScreenState extends State<PinChangeScreen> {
  final TextEditingController _pin = TextEditingController();
  final TextEditingController _repeat = TextEditingController();
  late String? _cardId = widget.cardId;
  String? _error;
  bool _done = false;

  void _submit() {
    String? error;
    if (_cardId == null) {
      error = 'Выберите карту';
    } else if (!RegExp(r'^\d{4}$').hasMatch(_pin.text)) {
      error = 'PIN-код - это 4 цифры';
    } else if (_pin.text != _repeat.text) {
      error = 'PIN-коды не совпадают';
    }
    setState(() {
      _error = error;
      _done = error == null;
    });
  }

  @override
  void dispose() {
    _pin.dispose();
    _repeat.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final store = DemoBankScope.of(context).store;
    final card = store.cards.where((c) => c.id == _cardId).firstOrNull;

    return Scaffold(
      appBar: demoAppBar('Смена PIN-кода'),
      body: _done && card != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.check_circle, size: 64, color: Colors.green.shade600),
                    const SizedBox(height: 12),
                    Text('PIN-код изменён', style: Theme.of(context).textTheme.titleLarge),
                    Text('${card.title} ${card.maskedNumber}'),
                    const SizedBox(height: 8),
                    const Text('Демо: настоящий PIN-код не менялся.'),
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: () => Navigator.of(context).pop(),
                      child: const Text('Готово'),
                    ),
                  ],
                ),
              ),
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const InfoBanner(text: 'Демо: PIN-код карты по-настоящему не меняется.'),
                const SectionTitle('Карта'),
                for (final c in store.cards)
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.credit_card),
                      title: Text(c.title),
                      subtitle: Text(c.maskedNumber),
                      selected: c.id == _cardId,
                      trailing: c.id == _cardId ? const Icon(Icons.check_circle) : null,
                      onTap: () => setState(() => _cardId = c.id),
                    ),
                  ),
                const SizedBox(height: 16),
                TextField(
                  controller: _pin,
                  obscureText: true,
                  keyboardType: TextInputType.number,
                  maxLength: 4,
                  decoration: const InputDecoration(
                    labelText: 'Новый PIN-код',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _repeat,
                  obscureText: true,
                  keyboardType: TextInputType.number,
                  maxLength: 4,
                  decoration: const InputDecoration(
                    labelText: 'Повторите PIN-код',
                    border: OutlineInputBorder(),
                  ),
                ),
                if (_error != null) ErrorText(_error!),
                const SizedBox(height: 8),
                FilledButton(onPressed: _submit, child: const Text('Сменить PIN-код')),
              ],
            ),
    );
  }
}
