import 'package:flutter/foundation.dart';

/// Счёт тестового клиента (вымышленный).
class BankAccount {
  BankAccount({
    required this.id,
    required this.title,
    required this.currency,
    required this.balance,
  });

  final String id;
  final String title;
  final String currency;
  double balance;
}

/// Карта тестового клиента (вымышленная).
class BankCard {
  const BankCard({
    required this.id,
    required this.title,
    required this.maskedNumber,
  });

  final String id;
  final String title;
  final String maskedNumber;
}

/// Проведённый в демо перевод.
class TransferRecord {
  const TransferRecord({required this.phone, required this.amount});

  final String phone;
  final double amount;
}

/// Вымышленный клиент демо-банка.
///
/// Данные живут только в памяти: после перезапуска приложения всё
/// возвращается к исходному состоянию. Настоящих счетов здесь нет.
class FakeBankStore extends ChangeNotifier {
  static const String demoPhone = '+996 555 000 000';
  static const String demoPin = '1234';

  final String clientName = 'Тестовый клиент';

  final List<BankAccount> accounts = [
    BankAccount(id: 'kgs', title: 'Текущий счёт', currency: 'KGS', balance: 25000),
    BankAccount(id: 'usd', title: 'Счёт в долларах', currency: 'USD', balance: 300),
  ];

  final List<BankCard> cards = const [
    BankCard(id: 'visa-gold', title: 'Visa Gold', maskedNumber: '•• 4821'),
    BankCard(id: 'elkart', title: 'ЭЛКАРТ', maskedNumber: '•• 1093'),
  ];

  final List<TransferRecord> transfers = [];

  String? _token;

  /// Токен клиента, который приложение передаёт ассистенту (вымышленный).
  String? get token => _token;

  /// Счёт в сомах: с него идут переводы по номеру телефона.
  BankAccount get kgsAccount => accounts.firstWhere((a) => a.currency == 'KGS');

  bool login(String pin) {
    if (pin != demoPin) return false;
    _token = 'demo-token-${DateTime.now().millisecondsSinceEpoch}';
    notifyListeners();
    return true;
  }

  void logout() {
    _token = null;
    notifyListeners();
  }

  bool checkPin(String pin) => pin == demoPin;

  /// Проводит вымышленный перевод со счёта в сомах. Текст ошибки или null.
  String? transfer({required String phone, required double amount}) {
    final account = kgsAccount;
    if (amount < 1) return 'Укажите сумму не меньше 1 сома';
    if (amount > account.balance) return 'Недостаточно средств на счёте';
    account.balance -= amount;
    transfers.insert(0, TransferRecord(phone: phone, amount: amount));
    notifyListeners();
    return null;
  }
}
