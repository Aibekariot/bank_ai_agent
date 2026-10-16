import 'package:flutter/material.dart';

import '../data/fake_bank_store.dart';
import '../format.dart';
import '../scope.dart';
import '../widgets/demo_widgets.dart';

enum _Step { form, confirm, done }

/// Перевод по номеру телефона: форма, подтверждение PIN-кодом, результат.
///
/// Ассистент может только заполнить форму ([phone], [amount]). Перевод
/// проходит, когда клиент сам проверил данные и подтвердил его PIN-кодом.
class TransferScreen extends StatefulWidget {
  const TransferScreen({super.key, this.phone, this.amount, this.fromAssistant = false});

  final String? phone;
  final num? amount;

  /// Форму заполнил ассистент: показываем предупреждение проверить данные.
  final bool fromAssistant;

  @override
  State<TransferScreen> createState() => _TransferScreenState();
}

class _TransferScreenState extends State<TransferScreen> {
  late final TextEditingController _phone =
      TextEditingController(text: widget.phone == null ? '' : formatPhone(widget.phone!));
  late final TextEditingController _amount =
      TextEditingController(text: widget.amount == null ? '' : _amountText(widget.amount!));
  final TextEditingController _pin = TextEditingController();

  _Step _step = _Step.form;
  String? _error;
  String? _recipient;
  double? _sum;

  static String _amountText(num value) =>
      value == value.roundToDouble() ? value.toInt().toString() : value.toStringAsFixed(2);

  void _continue() {
    final phone = normalizeKgPhone(_phone.text);
    final sum = double.tryParse(_amount.text.replaceAll(' ', '').replaceAll(',', '.'));
    final balance = DemoBankScope.of(context).store.kgsAccount.balance;

    String? error;
    if (phone == null) {
      error = 'Введите номер мобильного телефона в Кыргызстане, например 0555 123 456';
    } else if (sum == null || sum < 1) {
      error = 'Укажите сумму не меньше 1 сома';
    } else if (sum > balance) {
      error = 'Недостаточно средств на счёте';
    }

    setState(() {
      _error = error;
      if (error == null) {
        _recipient = phone;
        _sum = sum;
        _step = _Step.confirm;
      }
    });
  }

  void _confirm() {
    final store = DemoBankScope.of(context).store;
    if (!store.checkPin(_pin.text)) {
      setState(() => _error = 'Неверный PIN-код');
      return;
    }
    final error = store.transfer(phone: _recipient!, amount: _sum!);
    setState(() {
      _error = error;
      if (error == null) _step = _Step.done;
    });
  }

  void _backToForm() => setState(() {
        _step = _Step.form;
        _error = null;
        _pin.clear();
      });

  @override
  void dispose() {
    _phone.dispose();
    _amount.dispose();
    _pin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: demoAppBar('Перевод по номеру'),
      body: switch (_step) {
        _Step.form => _buildForm(context),
        _Step.confirm => _buildConfirm(context),
        _Step.done => _buildDone(context),
      },
    );
  }

  Widget _buildForm(BuildContext context) {
    final account = DemoBankScope.of(context).store.kgsAccount;
    final prefilled = widget.fromAssistant && (widget.phone != null || widget.amount != null);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (prefilled) ...[
          const InfoBanner(
            icon: Icons.support_agent,
            text: 'Данные заполнены ассистентом. Проверьте их: перевод выполнится '
                'только после вашего подтверждения.',
          ),
          const SizedBox(height: 12),
        ],
        Card(
          child: ListTile(
            leading: const Icon(Icons.account_balance_wallet_outlined),
            title: Text('Со счёта: ${account.title}'),
            subtitle: Text('Доступно: ${formatMoney(account.balance, account.currency)}'),
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _phone,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(
            labelText: 'Номер получателя',
            hintText: '0555 123 456',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Сумма, сом',
            border: OutlineInputBorder(),
          ),
        ),
        if (_error != null) ErrorText(_error!),
        const SizedBox(height: 12),
        FilledButton(onPressed: _continue, child: const Text('Продолжить')),
      ],
    );
  }

  Widget _buildConfirm(BuildContext context) {
    final account = DemoBankScope.of(context).store.kgsAccount;
    Widget row(String title, String value) => ListTile(
          dense: true,
          title: Text(title),
          trailing: Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        );
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Проверьте перевод', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Card(
          child: Column(
            children: [
              row('Получатель', formatPhone(_recipient!)),
              row('Сумма', formatMoney(_sum!, 'KGS')),
              row('Со счёта', account.title),
            ],
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _pin,
          obscureText: true,
          keyboardType: TextInputType.number,
          maxLength: 4,
          decoration: const InputDecoration(
            labelText: 'PIN-код для подтверждения',
            helperText: 'Демо: PIN ${FakeBankStore.demoPin}',
            border: OutlineInputBorder(),
          ),
        ),
        if (_error != null) ErrorText(_error!),
        const SizedBox(height: 8),
        FilledButton(onPressed: _confirm, child: const Text('Подтвердить перевод')),
        TextButton(onPressed: _backToForm, child: const Text('Изменить данные')),
      ],
    );
  }

  Widget _buildDone(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle, size: 64, color: Colors.green.shade600),
            const SizedBox(height: 12),
            Text('Перевод выполнен', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text('${formatMoney(_sum!, 'KGS')} на ${formatPhone(_recipient!)}'),
            const SizedBox(height: 8),
            const Text(
              'Демо: деньги никуда не ушли, изменился только вымышленный баланс.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Готово'),
            ),
          ],
        ),
      ),
    );
  }
}
