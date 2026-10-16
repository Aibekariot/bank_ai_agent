import 'package:flutter/material.dart';

import '../data/demo_bank_api.dart';
import '../format.dart';
import '../scope.dart';
import '../widgets/demo_widgets.dart';

/// Курсы валют. [currency] выделяется в таблице (приходит от ассистента).
class ExchangeRatesScreen extends StatefulWidget {
  const ExchangeRatesScreen({super.key, this.currency});

  final String? currency;

  @override
  State<ExchangeRatesScreen> createState() => _ExchangeRatesScreenState();
}

class _ExchangeRatesScreenState extends State<ExchangeRatesScreen> {
  Future<RatesData>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future ??= DemoBankScope.of(context).api.rates();
  }

  void _reload() => setState(() => _future = DemoBankScope.of(context).api.rates());

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: demoAppBar('Курсы валют'),
      body: FutureBuilder<RatesData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return ErrorRetry(message: describeError(snapshot.error), onRetry: _reload);
          }
          final data = snapshot.requireData;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('Курсы на ${data.date}', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 12),
              _RatesTable(title: 'Наличные', rates: data.cash, highlight: widget.currency),
              const SizedBox(height: 16),
              _RatesTable(title: 'Безналичные', rates: data.cashless, highlight: widget.currency),
              if (data.note.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 16),
                  child: Text(data.note, style: Theme.of(context).textTheme.bodySmall),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _RatesTable extends StatelessWidget {
  const _RatesTable({required this.title, required this.rates, this.highlight});

  final String title;
  final List<ExchangeRate> rates;
  final String? highlight;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    TableRow row(List<String> cells, {bool header = false, bool marked = false}) => TableRow(
          decoration: marked ? BoxDecoration(color: theme.colorScheme.primaryContainer) : null,
          children: [
            for (final cell in cells)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
                child: Text(
                  cell,
                  style: TextStyle(
                    fontWeight: header || marked ? FontWeight.w600 : FontWeight.normal,
                  ),
                ),
              ),
          ],
        );

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            if (rates.isEmpty)
              const Text('Нет данных')
            else
              Table(
                children: [
                  row(['Валюта', 'Покупка', 'Продажа'], header: true),
                  for (final rate in rates)
                    row(
                      [rate.currency, formatRate(rate.buy), formatRate(rate.sell)],
                      marked: rate.currency == highlight,
                    ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
