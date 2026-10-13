import 'package:flutter/material.dart';

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

  final List<ChatMessage> _messages = [
    ChatMessage(
      role: 'model',
      text:
          'Здравствуйте! Я AI-консультант Элдик Банка. '
          'Могу рассказать о кредитах, депозитах, курсах валют '
          'и помочь с расчётами. Чем могу помочь?',
    ),
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

      setState(() {
        _messages.add(
          ChatMessage(
            role: 'model',
            text:
                'Извините, произошла ошибка связи с сервером. '
                'Попробуйте ещё раз.\n($e)',
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