/// Сумма с пробелами между тысячами: 25000 -> "25 000 KGS", 1500.5 -> "1 500,50 KGS".
String formatMoney(num value, String currency) {
  final cents = (value.abs() * 100).round();
  final digits = (cents ~/ 100).toString();
  final buffer = StringBuffer(value < 0 ? '-' : '');
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buffer.write(' ');
    buffer.write(digits[i]);
  }
  final fraction = cents % 100;
  if (fraction != 0) buffer.write(',${fraction.toString().padLeft(2, '0')}');
  return '$buffer $currency';
}

/// Курс с двумя знаками: 87.3 -> "87,30".
String formatRate(num value) => value.toStringAsFixed(2).replaceAll('.', ',');

/// Мобильный номер Кыргызстана в виде +996XXXXXXXXX или null.
///
/// Те же правила, что у normalize_kg_phone на сервере: принимает
/// 0555 123 456, 555123456, 996555123456, +996 (555) 12-34-56.
String? normalizeKgPhone(String raw) {
  var digits = raw.replaceAll(RegExp(r'\D'), '');
  if (digits.length == 12 && digits.startsWith('996')) {
    digits = digits.substring(3);
  } else if (digits.length == 10 && digits.startsWith('0')) {
    digits = digits.substring(1);
  }
  if (digits.length != 9) return null;
  return '+996$digits';
}

/// +996555123456 -> "+996 555 123 456".
String formatPhone(String phone) {
  final normalized = normalizeKgPhone(phone);
  if (normalized == null) return phone;
  final d = normalized.substring(4);
  return '+996 ${d.substring(0, 3)} ${d.substring(3, 6)} ${d.substring(6)}';
}
