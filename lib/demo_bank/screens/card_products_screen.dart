import 'package:flutter/material.dart';

import '../data/demo_bank_api.dart';
import '../scope.dart';
import '../widgets/demo_widgets.dart';

/// Список карт банка для физических лиц.
class CardProductsScreen extends StatefulWidget {
  const CardProductsScreen({super.key});

  @override
  State<CardProductsScreen> createState() => _CardProductsScreenState();
}

class _CardProductsScreenState extends State<CardProductsScreen> {
  Future<List<CardProductSummary>>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future ??= DemoBankScope.of(context).api.cards();
  }

  void _reload() => setState(() => _future = DemoBankScope.of(context).api.cards());

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: demoAppBar('Карты банка'),
      body: FutureBuilder<List<CardProductSummary>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return ErrorRetry(message: describeError(snapshot.error), onRetry: _reload);
          }
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              for (final card in snapshot.requireData)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.credit_card),
                    title: Text(card.name),
                    subtitle: card.category == null ? null : Text(card.category!),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => CardProductScreen(slug: card.slug, title: card.name),
                    )),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

/// Страница карты. Стоимость null показывается как «не указано», а не «бесплатно».
class CardProductScreen extends StatefulWidget {
  const CardProductScreen({super.key, required this.slug, this.title});

  final String slug;
  final String? title;

  @override
  State<CardProductScreen> createState() => _CardProductScreenState();
}

class _CardProductScreenState extends State<CardProductScreen> {
  Future<CardProduct>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future ??= DemoBankScope.of(context).api.card(widget.slug);
  }

  void _reload() =>
      setState(() => _future = DemoBankScope.of(context).api.card(widget.slug));

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: demoAppBar(widget.title ?? 'Карта'),
      body: FutureBuilder<CardProduct>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return ErrorRetry(message: describeError(snapshot.error), onRetry: _reload);
          }
          final card = snapshot.requireData;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(card.name, style: theme.textTheme.headlineSmall),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  for (final tag in [card.category, card.paymentSystem, ...card.currencies])
                    if (tag != null) Chip(label: Text(tag)),
                ],
              ),
              const SizedBox(height: 12),
              _Fact('Выпуск', card.issuance),
              _Fact('Обслуживание в год', card.annualService),
              _Fact('Срок действия', card.expiration),
              if (card.partialData) ...[
                const SizedBox(height: 12),
                const InfoBanner(
                  text: 'Здесь только краткие условия. Подробности уточняйте '
                      'в контакт-центре 9111.',
                ),
              ],
              if (card.details.isNotEmpty) ...[
                const SectionTitle('Условия'),
                Text(card.details),
              ],
              const SizedBox(height: 20),
              FilledButton.icon(
                icon: const Icon(Icons.add_card),
                label: const Text('Оформить карту'),
                onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('В демо-приложении оформление недоступно')),
                ),
              ),
              if (card.dataDate != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text('Данные на ${card.dataDate}', style: theme.textTheme.bodySmall),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _Fact extends StatelessWidget {
  const _Fact(this.title, this.value);

  final String title;
  final String? value;

  @override
  Widget build(BuildContext context) => ListTile(
        contentPadding: EdgeInsets.zero,
        dense: true,
        title: Text(title),
        // null в данных значит «не указано», а не «бесплатно».
        trailing: Text(value ?? 'не указано'),
      );
}
