import 'package:flutter/widgets.dart';

/// Действие, которое ассистент предлагает выполнить в приложении.
///
/// Каталог действий и параметров: contract/actions.json. Ассистент только
/// предлагает: выполняет действие приложение, а операции (переводы)
/// клиент подтверждает сам на экране приложения.
@immutable
class AssistantAction {
  const AssistantAction({
    required this.name,
    required this.label,
    this.params = const {},
  });

  final String name;

  /// Подпись кнопки от сервера (запасная, приложение может дать свою).
  final String label;

  final Map<String, Object?> params;

  /// Действие из JSON ответа сервера; null, если данные не похожи на действие.
  static AssistantAction? tryParse(Object? json) {
    if (json is! Map) return null;
    final name = json['name'];
    if (name is! String || name.isEmpty) return null;
    final label = json['label'];
    final params = json['params'];
    return AssistantAction(
      name: name,
      label: label is String && label.isNotEmpty ? label : name,
      params: params is Map<String, Object?> ? params : const {},
    );
  }

  /// Непустой строковый параметр или null.
  String? stringParam(String key) {
    final value = params[key];
    return value is String && value.isNotEmpty ? value : null;
  }

  /// Числовой параметр или null.
  num? numberParam(String key) {
    final value = params[key];
    return value is num ? value : null;
  }
}

/// Выполняет действия ассистента в приложении-хозяине.
abstract interface class AssistantActionHandler {
  /// Действия, которые приложение умеет выполнять. Остальные не показываются.
  Set<String> get supportedActions;

  /// Подпись кнопки для действия.
  String labelFor(AssistantAction action);

  /// Выполняет действие: открывает экран приложения.
  Future<void> handle(BuildContext context, AssistantAction action);
}
