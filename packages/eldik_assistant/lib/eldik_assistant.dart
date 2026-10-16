/// Модуль чата ИИ-ассистента для приложения банка.
///
/// Приложение-хозяин передаёт адрес сервера и токен клиента
/// ([AssistantConfig]) и выполняет действия ассистента
/// ([AssistantActionHandler]). Контракт с сервером: contract/README.md.
library;

export 'src/assistant_action.dart';
export 'src/assistant_api.dart';
export 'src/assistant_chat_screen.dart';
export 'src/assistant_config.dart';
export 'src/chat_message.dart';
