import 'package:flutter/material.dart';
import '../models/watchlist_item.dart';
import '../repositories/watchlist_repository.dart';
import '../repositories/watchlist_editor.dart';

Future<bool> showWatchlistManagement(
  BuildContext context,
  WatchlistRepository repository,
) async {
  if (repository is! WatchlistEditor) return false;
  return await showModalBottomSheet<bool>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        isDismissible: false,
        enableDrag: false,
        builder: (_) => WatchlistManagementSheet(
          repository: repository,
          editor: repository as WatchlistEditor,
        ),
      ) ??
      false;
}

class WatchlistManagementSheet extends StatefulWidget {
  const WatchlistManagementSheet({
    super.key,
    required this.repository,
    required this.editor,
  });
  final WatchlistRepository repository;
  final WatchlistEditor editor;
  @override
  State<WatchlistManagementSheet> createState() =>
      _WatchlistManagementSheetState();
}

class _WatchlistManagementSheetState extends State<WatchlistManagementSheet> {
  List<WatchlistItem>? _items;
  Object? _error;
  bool _loading = true;
  bool _busy = false;
  bool _deleting = false;
  bool _changed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await widget.repository.fetchWatchlist();
      if (mounted) setState(() => _items = items);
    } catch (error) {
      if (mounted) setState(() => _error = error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _delete(WatchlistItem item) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('관심 종목 삭제'),
          content: Text(
            '${item.stockName} (${item.stockCode})을 관심 목록에서 삭제할까요?\n이 종목의 관심 알림 설정도 함께 제거됩니다. 보유 내역과 저장된 분석·뉴스·알림 이력은 유지됩니다.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('취소'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('삭제'),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
      setState(() => _deleting = true);
      await widget.editor.deleteStock(item.watchlistId);
      if (mounted) {
        setState(() {
          _items = _items!
              .where((value) => value.watchlistId != item.watchlistId)
              .toList();
          _changed = true;
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = error);
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _deleting = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    onPopInvokedWithResult: (didPop, result) {
      if (!didPop && !_busy) Navigator.pop(context, _changed);
    },
    child: SizedBox(
      height: MediaQuery.sizeOf(context).height * .75,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    '관심 목록 관리',
                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900),
                  ),
                ),
                IconButton(
                  onPressed: _busy
                      ? null
                      : () => Navigator.pop(context, _changed),
                  tooltip: '닫기',
                  icon: const Icon(Icons.close),
                ),
              ],
            ),
            const Text('종목별 삭제 버튼으로 관심 목록을 정리할 수 있습니다.'),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text(
                  '관심 목록 처리 실패 · $_error',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            if (_error != null)
              TextButton(
                onPressed: _busy || _loading ? null : _load,
                child: const Text('목록 다시 조회'),
              ),
            if (_deleting) const LinearProgressIndicator(),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _items == null
                  ? const Center(child: Text('관심 목록을 불러오지 못했습니다.'))
                  : _items!.isEmpty
                  ? const Center(child: Text('등록된 관심 종목이 없습니다.'))
                  : ListView.separated(
                      itemCount: _items!.length,
                      separatorBuilder: (_, index) => const Divider(),
                      itemBuilder: (context, index) {
                        final item = _items![index];
                        return ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(item.stockName),
                          subtitle: Text(
                            '${item.stockCode} · ${item.market} · 알림 ${item.alertEnabled ? '켜짐' : '꺼짐'}',
                          ),
                          trailing: IconButton(
                            onPressed: _busy ? null : () => _delete(item),
                            tooltip: '${item.stockName} 관심 종목 삭제',
                            icon: const Icon(Icons.delete_outline),
                          ),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    ),
  );
}
