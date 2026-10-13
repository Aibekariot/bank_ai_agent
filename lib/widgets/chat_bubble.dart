
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;

import '../models/message.dart';

class ChatBubble extends StatelessWidget {
  final ChatMessage message;

  const ChatBubble({super.key, required this.message});

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

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
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
      ),
    );
  }
}
