import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/message.dart';
import '../services/api_service.dart';
import '../widgets/chat_bubble.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final ApiService _apiService = ApiService();

  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _inputFocusNode = FocusNode();

  static const String _greeting =
      'Здравствуйте! Я AI-консультант Элдик Банка. '
      'Могу рассказать о кредитах, депозитах, курсах валют '
      'и помочь с расчётами. Чем могу помочь?';

  final List<ChatMessage> _messages = [
    ChatMessage(role: 'model', text: _greeting),
  ];

  bool _isLoading = false;

  /// true, если пользователь находится у нижнего края списка.
  bool _stickToBottom = true;
  double _lastKeyboardInset = 0;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    // Запас 80px: считаем, что пользователь "внизу", если он почти у края.
    _stickToBottom = position.maxScrollExtent - position.pixels <= 80;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    final inset = MediaQuery.viewInsetsOf(context).bottom;

    if (inset != _lastKeyboardInset) {
      _lastKeyboardInset = inset;

      // Клавиатура двигается (открывается/закрывается):
      // если пользователь был внизу, держим последнее сообщение видимым.
      if (_stickToBottom) {
        _scrollToBottom();
      }
    }
  }

  void _scrollToBottom({bool animated = false}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;

      final position = _scrollController.position;
      if (!position.hasContentDimensions) return;

      final target = position.maxScrollExtent;

      if (animated) {
        _scrollController.animateTo(
          target,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      } else {
        _scrollController.jumpTo(target);
      }
    });
  }

  Future<void> _sendMessage() async {
    final text = _controller.text.trim();

    if (text.isEmpty || _isLoading) return;

    setState(() {
      _messages.add(ChatMessage(role: 'user', text: text));

      _isLoading = true;
      _controller.clear();
    });

    // Пользователь сам отправил сообщение — всегда прижимаем к низу.
    _stickToBottom = true;
    _scrollToBottom(animated: true);

    try {
      final reply = await _apiService.sendMessage(_messages);

      if (!mounted) return;

      setState(() {
        _messages.add(ChatMessage(role: 'model', text: reply));
      });
    } catch (e) {
      if (!mounted) return;

      // Технические подробности только в консоль, пользователю - понятный текст.
      debugPrint('sendMessage error: $e');

      setState(() {
        _messages.add(
          ChatMessage(
            role: 'model',
            text: e is ApiException
                ? e.message
                : 'Извините, произошла ошибка связи с сервером. '
                    'Попробуйте ещё раз.',
            isError: true,
          ),
        );
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });

        _scrollToBottom(animated: true);
      }
    }
  }

  /// Весь диалог одним текстом: "Вопрос: ... / Ответ: ...".
  /// Приветствие в начале не включается.
  String _conversationAsText() {
    final buffer = StringBuffer();

    for (final message in _messages) {
      if (!message.isUser && message.text == _greeting) continue;

      buffer.writeln(
        message.isUser ? 'Вопрос: ${message.text}' : 'Ответ: ${message.text}',
      );
      buffer.writeln();
    }

    return buffer.toString().trim();
  }

  Future<void> _copyConversation() async {
    final text = _conversationAsText();

    if (text.isEmpty) {
      _showHint('Пока нечего копировать');
      return;
    }

    await Clipboard.setData(ClipboardData(text: text));

    if (!mounted) return;
    _showHint('Весь диалог скопирован');
  }

  void _startNewConversation() {
    if (_isLoading) return;

    setState(() {
      _messages
        ..clear()
        ..add(ChatMessage(role: 'model', text: _greeting));
    });

    _stickToBottom = true;
    _showHint('Новый диалог');
  }

  void _showHint(String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(text),
          duration: const Duration(seconds: 1),
        ),
      );
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _inputFocusNode.dispose();
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      resizeToAvoidBottomInset: true,
      appBar: AppBar(
        title: const Text('Элдик Банк — AI-консультант'),
        backgroundColor: Colors.blue.shade700,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.copy_all),
            tooltip: 'Скопировать весь диалог',
            onPressed: _copyConversation,
          ),
          IconButton(
            icon: const Icon(Icons.add_comment_outlined),
            tooltip: 'Новый диалог',
            onPressed: _isLoading ? null : _startNewConversation,
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView.builder(
                controller: _scrollController,
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.manual,
                padding: const EdgeInsets.symmetric(
                  vertical: 12,
                  horizontal: 8,
                ),
                itemCount: _messages.length,
                itemBuilder: (context, index) {
                  return ChatBubble(message: _messages[index]);
                },
              ),
            ),

            if (_isLoading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: SizedBox(
                  height: 18,
                  width: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),

            _buildInputBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildInputBar() {
    return Padding(
      padding: const EdgeInsets.all(8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: TextField(
              controller: _controller,
              focusNode: _inputFocusNode,
              minLines: 1,
              maxLines: 5,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => _sendMessage(),
              decoration: InputDecoration(
                hintText: 'Спросите о курсе валют, кредите, депозите...',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 10,
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Padding(
            padding: const EdgeInsets.only(bottom: 2),
            child: IconButton(
              icon: const Icon(Icons.send),
              color: Colors.blue.shade700,
              onPressed: _isLoading ? null : _sendMessage,
            ),
          ),
        ],
      ),
    );
  }
}