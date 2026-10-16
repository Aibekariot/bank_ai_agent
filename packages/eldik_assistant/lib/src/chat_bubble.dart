import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;

import 'assistant_action.dart';
import 'chat_message.dart';

class ChatBubble extends StatelessWidget {
  const ChatBubble({
    super.key,
    required this.message,
    this.actions = const [],
    this.onAction,
    this.labelFor,
  });

  final ChatMessage message;

  /// Действия, которые приложение умеет выполнить (кнопки под ответом).
  final List<AssistantAction> actions;
  final void Function(AssistantAction action)? onAction;
  final String Function(AssistantAction action)? labelFor;

  List<String> _splitTableRow(String line) {
    var value = line.trim();

    if (value.startsWith('|')) {
      value = value.substring(1);
    }
    if (value.endsWith('|')) {
      value = value.substring(0, value.length - 1);
    }

    return value.split('|').map((cell) => cell.trim()).toList();
  }

  bool _isTableSeparator(String line) {
    if (!line.contains('|')) return false;

    final cells = _splitTableRow(line);
    if (cells.isEmpty) return false;

    return cells.every(
      (cell) => RegExp(r'^:?-{3,}:?$').hasMatch(cell),
    );
  }

  String _adaptTablesForMobile(String text) {
    final lines = text.split('\n');
    final output = <String>[];
    var i = 0;

    while (i < lines.length) {
      if (i + 1 < lines.length &&
          lines[i].contains('|') &&
          _isTableSeparator(lines[i + 1])) {
        final headers = _splitTableRow(lines[i]);
        i += 2;

        final rows = <List<String>>[];

        while (i < lines.length &&
            lines[i].contains('|') &&
            lines[i].trim().isNotEmpty) {
          rows.add(_splitTableRow(lines[i]));
          i++;
        }

        for (final row in rows) {
          final fields = <String>[];

          for (var column = 0; column < headers.length; column++) {
            if (column >= row.length || row[column].isEmpty) continue;

            fields.add(
              '- **${headers[column]}:** ${row[column]}',
            );
          }

          if (fields.isNotEmpty) {
            output.addAll(fields);
            output.add('');
          }
        }

        continue;
      }

      output.add(lines[i]);
      i++;
    }

    return output.join('\n').trim();
  }

  /// Копирует сообщение целиком (исходный текст, без адаптации таблиц).
  Future<void> _copyWholeMessage(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: message.text));

    if (!context.mounted) return;

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        const SnackBar(
          content: Text('Сообщение скопировано'),
          duration: Duration(seconds: 1),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    final screenWidth = MediaQuery.sizeOf(context).width;
    final isCompact = screenWidth < 600;

    final maxBubbleWidth = math.min(
      screenWidth * (isCompact ? 0.94 : 0.82),
      860.0,
    );

    final displayText = !isUser && isCompact
        ? _adaptTablesForMobile(message.text)
        : message.text;

    final theme = Theme.of(context);
    final textColor = isUser
        ? Colors.white
        : theme.colorScheme.onSurface;

    final markdownStyle = MarkdownStyleSheet.fromTheme(theme).copyWith(
      p: TextStyle(
        color: textColor,
        fontSize: 15,
        height: 1.45,
      ),
      h1: TextStyle(
        color: textColor,
        fontSize: 21,
        fontWeight: FontWeight.bold,
      ),
      h2: TextStyle(
        color: textColor,
        fontSize: 19,
        fontWeight: FontWeight.bold,
      ),
      h3: TextStyle(
        color: textColor,
        fontSize: 17,
        fontWeight: FontWeight.bold,
      ),
      listBullet: TextStyle(
        color: textColor,
        fontSize: 15,
      ),
    );

    final bubble = Container(
      constraints: BoxConstraints(maxWidth: maxBubbleWidth),
      margin: const EdgeInsets.symmetric(
        vertical: 4,
        horizontal: 10,
      ),
      padding: const EdgeInsets.symmetric(
        horizontal: 14,
        vertical: 10,
      ),
      decoration: BoxDecoration(
        color: isUser
            ? Colors.blue.shade700
            : theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(16),
      ),
      child: isUser
          ? SelectableText(
              displayText,
              style: TextStyle(
                color: textColor,
                fontSize: 15,
                height: 1.45,
              ),
            )
          : MarkdownBody(
              data: displayText,
              selectable: true,
              extensionSet: md.ExtensionSet.gitHubWeb,
              styleSheet: markdownStyle,
            ),
    );

    final mutedColor = theme.colorScheme.onSurfaceVariant;

    final copyButton = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => _copyWholeMessage(context),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.copy, size: 14, color: mutedColor),
              const SizedBox(width: 4),
              Text(
                'Копировать',
                style: TextStyle(fontSize: 12, color: mutedColor),
              ),
            ],
          ),
        ),
      ),
    );

    final onAction = this.onAction;
    final actionButtons = actions.isEmpty || onAction == null
        ? null
        : Padding(
            padding: const EdgeInsets.fromLTRB(10, 2, 10, 2),
            child: Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                for (final action in actions)
                  OutlinedButton.icon(
                    icon: const Icon(Icons.arrow_forward, size: 16),
                    label: Text(labelFor?.call(action) ?? action.label),
                    onPressed: () => onAction(action),
                  ),
              ],
            ),
          );

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment:
            isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [bubble, ?actionButtons, copyButton],
      ),
    );
  }
}
