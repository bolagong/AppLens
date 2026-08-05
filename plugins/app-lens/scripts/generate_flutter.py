#!/usr/bin/env python3
"""Generate an original, runnable Flutter reference prototype from a product model."""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

from model_tools import append_audit, load_model, write_json


def strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def prototype_payload(model: dict[str, Any]) -> dict[str, Any]:
    project = model.get("project", {})
    visual = model.get("visual_model", {}).get("decisions", {})
    primary = "#3454D1"
    if isinstance(visual, dict):
        for key in ("primary_color", "primaryColor", "accent_color", "accentColor"):
            candidate = visual.get(key)
            if isinstance(candidate, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", candidate):
                primary = candidate.upper()
                break
    functions = []
    for item in model.get("functions", []):
        if not isinstance(item, dict) or item.get("product_decision") == "delete":
            continue
        functions.append(
            {
                "name": str(item.get("name", "Untitled function")),
                "entry": str(item.get("entry", "")),
                "decision": str(item.get("product_decision", "modify")),
                "flow": strings(item.get("flow")),
                "pages": strings(item.get("pages")),
                "states": strings(item.get("page_states")),
                "rules": strings(item.get("interaction_rules")),
                "acceptance": strings(item.get("acceptance_criteria")),
            }
        )
    return {"title": str(project.get("name", "Product Reference")), "primary": primary, "functions": functions}


DART_TEMPLATE = r'''import 'dart:convert';

import 'package:flutter/material.dart';

final _model = jsonDecode(utf8.decode(base64Decode('__PAYLOAD__'))) as Map<String, dynamic>;
final _primary = Color(int.parse('FF${(_model['primary'] as String).replaceFirst('#', '')}', radix: 16));
final productFunctions = ((_model['functions'] as List<dynamic>)
        .whereType<Map<String, dynamic>>()
        .map(ProductFunction.fromJson))
    .toList();

void main() => runApp(const ReferenceApp());

class ProductFunction {
  ProductFunction.fromJson(this.data);
  final Map<String, dynamic> data;
  String get name => data['name'] as String;
  String get entry => data['entry'] as String;
  String get decision => data['decision'] as String;
  List<String> values(String key) => (data[key] as List<dynamic>).map((item) => item.toString()).toList();
}

class ReferenceApp extends StatefulWidget {
  const ReferenceApp({super.key});
  @override
  State<ReferenceApp> createState() => _ReferenceAppState();
}

class _ReferenceAppState extends State<ReferenceApp> {
  final Set<String> saved = <String>{};
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: _model['title'] as String,
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: _primary), useMaterial3: true),
        home: HomeScreen(saved: saved, onSaved: (name, value) => setState(() => value ? saved.add(name) : saved.remove(name))),
      );
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.saved, required this.onSaved});
  final Set<String> saved;
  final void Function(String name, bool value) onSaved;
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String query = '';
  String filter = 'all';
  @override
  Widget build(BuildContext context) {
    final visible = productFunctions.where((item) =>
        item.name.toLowerCase().contains(query.toLowerCase()) && (filter == 'all' || item.decision == filter)).toList();
    return Scaffold(
      appBar: AppBar(
        title: Text(_model['title'] as String),
        actions: [IconButton(tooltip: 'Saved', icon: Badge(isLabelVisible: widget.saved.isNotEmpty, label: Text('${widget.saved.length}'), child: const Icon(Icons.bookmark_outline)), onPressed: () => _showSaved(context))],
      ),
      body: Column(children: [
        Padding(padding: const EdgeInsets.fromLTRB(16, 16, 16, 6), child: TextField(onChanged: (value) => setState(() => query = value), decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Search reference functions', border: OutlineInputBorder()))),
        SingleChildScrollView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6), child: Row(children: ['all', 'keep', 'modify', 'add'].map((value) => Padding(padding: const EdgeInsets.only(right: 8), child: ChoiceChip(label: Text(value == 'all' ? 'All' : value), selected: filter == value, onSelected: (_) => setState(() => filter = value)))).toList())),
        Expanded(child: visible.isEmpty
            ? const Center(child: Column(mainAxisSize: MainAxisSize.min, children: [Icon(Icons.inbox_outlined, size: 44), SizedBox(height: 12), Text('No reference functions match this view.')]))
            : ListView.separated(padding: const EdgeInsets.all(16), itemCount: visible.length, separatorBuilder: (_, __) => const SizedBox(height: 10), itemBuilder: (context, index) {
                final item = visible[index];
                final saved = widget.saved.contains(item.name);
                return Card(child: ListTile(
                  leading: CircleAvatar(child: Text('${index + 1}')),
                  title: Text(item.name),
                  subtitle: Text(item.entry.isEmpty ? 'Entry to be defined in the product model' : item.entry),
                  trailing: IconButton(tooltip: saved ? 'Remove saved state' : 'Save reference function', icon: Icon(saved ? Icons.bookmark : Icons.bookmark_border), onPressed: () => widget.onSaved(item.name, !saved)),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DetailScreen(item: item, initiallySaved: saved, onSaved: widget.onSaved))),
                ));
              }))
      ]),
    );
  }

  void _showSaved(BuildContext context) {
    final items = productFunctions.where((item) => widget.saved.contains(item.name)).toList();
    showModalBottomSheet<void>(context: context, builder: (_) => SafeArea(child: items.isEmpty ? const Padding(padding: EdgeInsets.all(32), child: Text('No saved functions yet.')) : ListView(shrinkWrap: true, children: items.map((item) => ListTile(title: Text(item.name), trailing: IconButton(icon: const Icon(Icons.bookmark), onPressed: () { widget.onSaved(item.name, false); Navigator.pop(context); }))).toList())));
  }
}

class DetailScreen extends StatefulWidget {
  const DetailScreen({super.key, required this.item, required this.initiallySaved, required this.onSaved});
  final ProductFunction item;
  final bool initiallySaved;
  final void Function(String name, bool value) onSaved;
  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  late bool saved = widget.initiallySaved;
  bool loading = false;
  bool failure = false;
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.item.name), actions: [IconButton(icon: Icon(saved ? Icons.bookmark : Icons.bookmark_border), onPressed: () => setState(() { saved = !saved; widget.onSaved(widget.item.name, saved); }))]),
    body: ListView(padding: const EdgeInsets.all(16), children: [
      Text(widget.item.decision.toUpperCase(), style: Theme.of(context).textTheme.labelLarge?.copyWith(color: _primary)),
      const SizedBox(height: 8), Text(widget.item.entry.isEmpty ? 'Entry to be defined in the product model.' : widget.item.entry, style: Theme.of(context).textTheme.titleMedium), const SizedBox(height: 20),
      _Section('Flow', widget.item.values('flow')), _Section('Pages', widget.item.values('pages')), _Section('Interaction rules', widget.item.values('rules')), _Section('Acceptance criteria', widget.item.values('acceptance')),
      SwitchListTile(value: loading, title: const Text('Demonstrate loading state'), onChanged: (value) => setState(() { loading = value; if (value) failure = false; })),
      SwitchListTile(value: failure, title: const Text('Demonstrate failure state'), onChanged: (value) => setState(() { failure = value; if (value) loading = false; })),
      if (loading) const _StateCard(Icons.hourglass_top, 'Loading mock content…'),
      if (failure) const _StateCard(Icons.error_outline, 'Mock failure state. Retry remains local.'),
    ]),
  );
}

class _Section extends StatelessWidget {
  const _Section(this.title, this.items);
  final String title;
  final List<String> items;
  @override
  Widget build(BuildContext context) => items.isEmpty ? const SizedBox.shrink() : Padding(padding: const EdgeInsets.only(bottom: 16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: Theme.of(context).textTheme.titleSmall), const SizedBox(height: 6), ...items.map((item) => Padding(padding: const EdgeInsets.only(bottom: 4), child: Text('• $item')))]));
}

class _StateCard extends StatelessWidget {
  const _StateCard(this.icon, this.message);
  final IconData icon;
  final String message;
  @override
  Widget build(BuildContext context) => Card(child: Padding(padding: const EdgeInsets.all(16), child: Row(children: [Icon(icon), const SizedBox(width: 12), Expanded(child: Text(message))])));
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="Replace an existing generated Flutter prototype")
    arguments = parser.parse_args()
    output_dir = arguments.output.expanduser().resolve()
    prototype_dir = output_dir / "flutter_prototype"
    main_path = prototype_dir / "lib" / "main.dart"
    if main_path.exists() and not arguments.force:
        print("Flutter prototype already exists. Pass --force to regenerate it.", file=sys.stderr)
        return 2
    try:
        model = load_model(output_dir)
        payload = base64.b64encode(json.dumps(prototype_payload(model), ensure_ascii=False).encode("utf-8")).decode("ascii")
        main_path.parent.mkdir(parents=True, exist_ok=True)
        (prototype_dir / "test").mkdir(parents=True, exist_ok=True)
        (prototype_dir / "pubspec.yaml").write_text("""name: product_reference_prototype
description: Original local Flutter reference prototype generated from a product model.
publish_to: none
version: 0.1.0+1
environment:
  sdk: '>=3.0.0 <4.0.0'
dependencies:
  flutter:
    sdk: flutter
dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^5.0.0
flutter:
  uses-material-design: true
""", encoding="utf-8")
        main_path.write_text(DART_TEMPLATE.replace("__PAYLOAD__", payload), encoding="utf-8")
        (prototype_dir / "test" / "widget_test.dart").write_text("""import 'package:flutter_test/flutter_test.dart';
import 'package:product_reference_prototype/main.dart';

void main() {
  testWidgets('renders the reference prototype shell', (tester) async {
    await tester.pumpWidget(const ReferenceApp());
    expect(find.byType(HomeScreen), findsOneWidget);
  });
}
""", encoding="utf-8")
        (prototype_dir / "README.md").write_text("# Original Flutter reference prototype\n\nGenerated from `project-model.json`. It uses original UI, mock data, and local state only.\n", encoding="utf-8")
        generation = model.setdefault("generation", {})
        generation["flutter_prototype_status"] = "generated"
        append_audit(model, "flutter_prototype_generated", {"path": "flutter_prototype", "function_count": len(prototype_payload(model)["functions"])})
        write_json(output_dir / "project-model.json", model)
    except (OSError, ValueError) as error:
        print(f"Flutter generation failed: {error}", file=sys.stderr)
        return 2
    print(prototype_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
