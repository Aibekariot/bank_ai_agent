/// Адрес сервера ассистента (он же отдаёт данные демо-банка).
///
/// Задаётся при запуске, без правки кода:
///   flutter run --dart-define=API_BASE_URL=http://192.168.0.10:8000
/// Для эмулятора Android адрес компьютера - http://10.0.2.2:8000.
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.179.11.28:8000',
);
