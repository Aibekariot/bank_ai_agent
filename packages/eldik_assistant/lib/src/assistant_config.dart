/// Настройки модуля ассистента, которые задаёт приложение-хозяин.
class AssistantConfig {
  const AssistantConfig({
    required this.baseUrl,
    this.authToken,
    this.sessionId,
    this.title = 'Ассистент',
    this.greeting = defaultGreeting,
    this.timeout = const Duration(seconds: 90),
  });

  /// Адрес сервера ассистента, например http://192.168.0.10:8000.
  final String baseUrl;

  /// Токен клиента из приложения (заголовок Authorization).
  final String? authToken;

  /// Идентификатор диалога.
  final String? sessionId;

  /// Заголовок экрана чата.
  final String title;

  /// Первое сообщение ассистента (на сервер не отправляется).
  final String greeting;

  /// Бесплатная модель отвечает до 25-40 секунд, берём с запасом.
  final Duration timeout;

  static const String defaultGreeting =
      'Здравствуйте! Я AI-консультант Элдик Банка. '
      'Расскажу о картах, кредитах, вкладах и курсах валют, найду банкомат '
      'и помогу открыть нужный раздел приложения. Чем могу помочь?';
}
