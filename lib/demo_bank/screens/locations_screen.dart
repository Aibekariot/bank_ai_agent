import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../data/demo_bank_api.dart';
import '../scope.dart';
import '../widgets/demo_widgets.dart';

/// Банкоматы и отделения. [city] и [kind] приходят от ассистента.
class LocationsScreen extends StatefulWidget {
  const LocationsScreen({super.key, this.city, this.kind});

  final String? city;
  final String? kind;

  /// Типы точек, как в contract/actions.json.
  static const Map<String, String> kinds = {
    '': 'Все',
    'atm': 'Банкоматы',
    'branch': 'Филиалы',
    'savings_cash': 'Сберкассы',
    'mobile_cash': 'Выездные кассы',
  };

  @override
  State<LocationsScreen> createState() => _LocationsScreenState();
}

class _LocationsScreenState extends State<LocationsScreen> {
  late final TextEditingController _query = TextEditingController(text: widget.city ?? '');
  late String _kind = LocationsScreen.kinds.containsKey(widget.kind) ? widget.kind! : '';
  Future<List<BankLocation>>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future ??= _load();
  }

  Future<List<BankLocation>> _load() =>
      DemoBankScope.of(context).api.locations(query: _query.text.trim(), kind: _kind);

  void _search() => setState(() => _future = _load());

  Future<void> _copyMapLink(String link) async {
    await Clipboard.setData(ClipboardData(text: link));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(const SnackBar(content: Text('Ссылка на карту скопирована')));
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: demoAppBar('Банкоматы и отделения'),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: TextField(
              controller: _query,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _search(),
              decoration: InputDecoration(
                labelText: 'Город, улица или район',
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  icon: const Icon(Icons.search),
                  tooltip: 'Найти',
                  onPressed: _search,
                ),
              ),
            ),
          ),
          SizedBox(
            height: 48,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              children: [
                for (final entry in LocationsScreen.kinds.entries)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: ChoiceChip(
                      label: Text(entry.value),
                      selected: _kind == entry.key,
                      onSelected: (_) {
                        _kind = entry.key;
                        _search();
                      },
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: FutureBuilder<List<BankLocation>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return ErrorRetry(message: describeError(snapshot.error), onRetry: _search);
                }
                final items = snapshot.requireData;
                if (items.isEmpty) {
                  return const Center(child: Text('Ничего не найдено'));
                }
                return ListView(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                  children: [
                    Text('Найдено: ${items.length}. Режим работы уточняйте '
                        'в контакт-центре 9111.'),
                    const SizedBox(height: 8),
                    for (final item in items)
                      Card(
                        child: ListTile(
                          isThreeLine: true,
                          title: Text(item.name),
                          subtitle: Text([
                            item.type,
                            item.address,
                            if (item.phones.isNotEmpty) item.phones.join(', '),
                          ].join('\n')),
                          trailing: item.mapLink == null
                              ? null
                              : IconButton(
                                  icon: const Icon(Icons.map_outlined),
                                  tooltip: 'Скопировать ссылку на карту',
                                  onPressed: () => _copyMapLink(item.mapLink!),
                                ),
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
