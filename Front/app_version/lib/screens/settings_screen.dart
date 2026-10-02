import 'package:flutter/material.dart';

import '../models/kb_account_snapshot.dart';
import '../models/provider_setting.dart';
import '../repositories/kb_account_repository.dart';
import '../repositories/provider_settings_repository.dart';
import '../services/app_security_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';
import 'kb_holdings_detail_dialog.dart';

/// 개인용 프로그램 설정 화면입니다.
class SettingsScreen extends StatelessWidget {
  /// 증권사 설정 Future와 재시도 콜백을 받습니다.
  const SettingsScreen({
    super.key,
    required this.providerSettingsFuture,
    required this.providerSettingsRepository,
    required this.kbAccountRepository,
    required this.appSecurityService,
    required this.appLockPinConfigured,
    required this.onAppLockPinChanged,
    required this.onRetry,
  });

  /// 백엔드에서 조회하는 증권사 설정 Future입니다.
  final Future<ProviderSettingsSnapshot> providerSettingsFuture;

  final ProviderSettingsRepository providerSettingsRepository;

  /// KB증권 계좌 조회 Repository입니다.
  final KbAccountRepository kbAccountRepository;

  /// 앱 잠금 PIN을 Windows Credential Manager에 저장합니다.
  final AppSecurityService appSecurityService;

  /// Credential Manager에 앱 잠금 PIN이 등록되어 있는지 여부입니다.
  final bool appLockPinConfigured;

  /// PIN 상태 변경을 앱 루트에 반영합니다.
  final ValueChanged<String?> onAppLockPinChanged;

  /// 설정 조회를 다시 시도하는 콜백입니다.
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return FutureBuilder<ProviderSettingsSnapshot>(
      future: providerSettingsFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }

        if (snapshot.hasError || !snapshot.hasData) {
          return _SettingsErrorState(onRetry: onRetry);
        }

        final settings = snapshot.data!;
        final providers = settings.providers;
        final kbProvider = _findProvider(providers, 'KB');

        return AppScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SectionHeader(
                eyebrow: '개인용 설정',
                title: '증권사 연동',
                action: StatusChip(
                  label: '로컬',
                  icon: Icons.computer_rounded,
                  gradient: AppGradients.main,
                ),
              ),
              const SizedBox(height: 10),
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '로컬 실행 상태',
                      style: TextStyle(
                        color: palette.text,
                        fontSize: 15,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 12),
                    const _SettingLine(
                      icon: Icons.person_rounded,
                      label: '사용자',
                      value: '개인 사용자',
                    ),
                    const SizedBox(height: 8),
                    const _SettingLine(
                      icon: Icons.lock_open_rounded,
                      label: '인증',
                      value: '로그인 없음',
                    ),
                    const SizedBox(height: 8),
                    const _SettingLine(
                      icon: Icons.dns_rounded,
                      label: 'API',
                      value: '로컬 Spring Boot',
                    ),
                    const SizedBox(height: 8),
                    _SettingLine(
                      icon: Icons.folder_rounded,
                      label: '서버 비밀값',
                      value: settings.secretStorageType,
                    ),
                    const SizedBox(height: 8),
                    _SettingLine(
                      icon: Icons.block_rounded,
                      label: '주문',
                      value: settings.orderSafetyMode,
                    ),
                    const SizedBox(height: 10),
                    Text(
                      settings.secretStorageDescription,
                      style: TextStyle(
                        color: palette.muted,
                        fontSize: 12,
                        height: 1.35,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              _AppLockCredentialCard(
                securityService: appSecurityService,
                configured: appLockPinConfigured,
                onChanged: onAppLockPinChanged,
              ),
              const SizedBox(height: 12),
              _MarketFallbackCard(settings: settings),
              const SizedBox(height: 12),
              if (settings.orderReadiness != null) ...[
                _OrderReadinessCard(
                  readiness: settings.orderReadiness!,
                  repository: providerSettingsRepository,
                ),
                const SizedBox(height: 12),
              ],
              ...providers.map(
                (provider) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _ProviderCard(
                    provider: provider,
                    marketDataPriority: settings.marketDataFallbackOrder
                        .indexOf(provider.code),
                  ),
                ),
              ),
              if (kbProvider != null) ...[
                const SizedBox(height: 2),
                _KbAccountSection(
                  provider: kbProvider,
                  repository: kbAccountRepository,
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _AppLockCredentialCard extends StatefulWidget {
  const _AppLockCredentialCard({
    required this.securityService,
    required this.configured,
    required this.onChanged,
  });

  final AppSecurityService securityService;
  final bool configured;
  final ValueChanged<String?> onChanged;

  @override
  State<_AppLockCredentialCard> createState() => _AppLockCredentialCardState();
}

class _AppLockCredentialCardState extends State<_AppLockCredentialCard> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.password_rounded, color: AppTheme.main),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Windows 앱 잠금',
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
              ),
              StatusChip(
                label: widget.configured ? '보호됨' : '설정 안 됨',
                icon: widget.configured
                    ? Icons.verified_user_rounded
                    : Icons.lock_open_rounded,
                gradient: widget.configured ? AppGradients.main : null,
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            '앱 잠금 PIN만 현재 Windows 사용자 Credential Manager에 저장합니다. Ubuntu의 증권사 키와 계좌번호는 서버에서 별도로 관리합니다.',
            style: TextStyle(
              color: palette.muted,
              fontSize: 12,
              height: 1.4,
              fontWeight: FontWeight.w700,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: _busy ? null : _savePin,
                  icon: _busy
                      ? const SizedBox.square(
                          dimension: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : Icon(
                          widget.configured
                              ? Icons.edit_rounded
                              : Icons.add_rounded,
                        ),
                  label: Text(widget.configured ? 'PIN 변경' : 'PIN 설정'),
                ),
              ),
              if (widget.configured) ...[
                const SizedBox(width: 8),
                IconButton.outlined(
                  onPressed: _busy ? null : _deletePin,
                  tooltip: '앱 잠금 PIN 삭제',
                  icon: const Icon(Icons.delete_outline_rounded),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _savePin() async {
    final pin = await showDialog<String>(
      context: context,
      builder: (_) => const _PinEditorDialog(),
    );
    if (pin == null || !mounted) return;

    setState(() => _busy = true);
    try {
      await widget.securityService.savePin(pin);
      widget.onChanged(pin);
      if (mounted) _showMessage('Windows Credential Manager에 PIN을 저장했습니다.');
    } catch (error) {
      if (mounted) _showMessage(error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _deletePin() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('앱 잠금 해제'),
        content: const Text('저장된 PIN을 삭제하면 다음 실행부터 잠금 화면을 표시하지 않습니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('PIN 삭제'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _busy = true);
    try {
      await widget.securityService.deletePin();
      widget.onChanged(null);
      if (mounted) _showMessage('앱 잠금 PIN을 삭제했습니다.');
    } catch (error) {
      if (mounted) _showMessage(error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

class _PinEditorDialog extends StatefulWidget {
  const _PinEditorDialog();

  @override
  State<_PinEditorDialog> createState() => _PinEditorDialogState();
}

class _PinEditorDialogState extends State<_PinEditorDialog> {
  final _pinController = TextEditingController();
  final _confirmController = TextEditingController();
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _pinController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('앱 잠금 PIN 설정'),
      content: SizedBox(
        width: 340,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _pinController,
              autofocus: true,
              obscureText: _obscure,
              keyboardType: TextInputType.number,
              maxLength: 12,
              decoration: InputDecoration(
                labelText: '새 PIN',
                errorText: _error,
                suffixIcon: IconButton(
                  onPressed: () => setState(() => _obscure = !_obscure),
                  tooltip: _obscure ? 'PIN 표시' : 'PIN 숨기기',
                  icon: Icon(
                    _obscure
                        ? Icons.visibility_rounded
                        : Icons.visibility_off_rounded,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _confirmController,
              obscureText: _obscure,
              keyboardType: TextInputType.number,
              maxLength: 12,
              onSubmitted: (_) => _submit(),
              decoration: const InputDecoration(labelText: 'PIN 확인'),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        FilledButton(onPressed: _submit, child: const Text('저장')),
      ],
    );
  }

  void _submit() {
    final pin = _pinController.text.trim();
    if (!RegExp(r'^\d{4,12}$').hasMatch(pin)) {
      setState(() => _error = '숫자 4~12자리로 입력해 주세요.');
      return;
    }
    if (pin != _confirmController.text.trim()) {
      setState(() => _error = 'PIN 확인 값이 일치하지 않습니다.');
      return;
    }
    Navigator.pop(context, pin);
  }
}

ProviderSetting? _findProvider(List<ProviderSetting> providers, String code) {
  for (final provider in providers) {
    if (provider.code == code) {
      return provider;
    }
  }

  return null;
}

class _OrderReadinessCard extends StatefulWidget {
  const _OrderReadinessCard({
    required this.readiness,
    required this.repository,
  });

  final OrderReadiness readiness;
  final ProviderSettingsRepository repository;

  @override
  State<_OrderReadinessCard> createState() => _OrderReadinessCardState();
}

class _OrderReadinessCardState extends State<_OrderReadinessCard> {
  bool _checking = false;
  bool _loadingLatest = true;
  int _probeVersion = 0;
  OrderReadOnlyProbe? _probe;
  String? _probeError;

  @override
  void initState() {
    super.initState();
    _loadLatestProbe();
  }

  Future<void> _loadLatestProbe() async {
    final version = _probeVersion;
    try {
      final result = await widget.repository
          .fetchLatestReadOnlyOrderHistoryProbe();
      if (mounted && version == _probeVersion) setState(() => _probe = result);
    } catch (_) {
      if (mounted && version == _probeVersion) {
        setState(() => _probeError = '마지막 점검 기록을 불러오지 못했습니다.');
      }
    } finally {
      if (mounted) setState(() => _loadingLatest = false);
    }
  }

  Future<void> _checkReadOnlyAccess() async {
    setState(() {
      _probeVersion++;
      _checking = true;
      _probeError = null;
    });
    try {
      final result = await widget.repository.probeReadOnlyOrderHistory();
      if (!mounted) return;
      setState(() => _probe = result);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _probeError = '조회 권한 점검에 실패했습니다. 서버 연결을 확인해 주세요.';
      });
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final passed = widget.readiness.checks
        .where((check) => check.passed)
        .length;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.verified_user_outlined, color: palette.text, size: 20),
              const SizedBox(width: 9),
              Expanded(
                child: Text(
                  'KB 실주문 준비 상태',
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              StatusChip(label: widget.readiness.canSubmit ? '가능' : '잠금'),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            '$passed/${widget.readiness.checks.length} 조건 확인',
            style: TextStyle(color: palette.muted, fontSize: 12),
          ),
          const SizedBox(height: 10),
          ...widget.readiness.checks.map(
            (check) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    check.passed
                        ? Icons.check_circle_outline_rounded
                        : Icons.error_outline_rounded,
                    color: check.passed
                        ? const Color(0xff17834a)
                        : const Color(0xffba5038),
                    size: 17,
                  ),
                  const SizedBox(width: 9),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _orderCheckLabel(check.code),
                          style: TextStyle(
                            color: palette.text,
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        if (!check.passed)
                          Text(
                            check.message,
                            style: TextStyle(
                              color: palette.muted,
                              fontSize: 11,
                              height: 1.3,
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _checking ? null : _checkReadOnlyAccess,
            icon: _checking
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.fact_check_outlined, size: 18),
            label: const Text('조회 권한 점검'),
          ),
          if (_probeError != null) ...[
            const SizedBox(height: 8),
            Text(
              _probeError!,
              style: const TextStyle(color: Color(0xffba5038), fontSize: 12),
            ),
          ],
          if (_probe != null) ...[
            const SizedBox(height: 8),
            Text(
              '마지막 점검 · ${_formatProbeTime(_probe!.checkedAt)}',
              style: TextStyle(color: palette.muted, fontSize: 11),
            ),
            const SizedBox(height: 3),
            Text(
              _probe!.message,
              style: TextStyle(
                color: _probe!.status == 'VERIFIED'
                    ? const Color(0xff17834a)
                    : const Color(0xffba5038),
                fontSize: 12,
                height: 1.35,
              ),
            ),
            Text(
              '과거 조회 결과이며 현재 주문 가능 여부를 뜻하지 않습니다.',
              style: TextStyle(color: palette.muted, fontSize: 11),
            ),
          ] else if (!_loadingLatest && _probeError == null) ...[
            const SizedBox(height: 8),
            Text(
              '마지막 점검 기록 없음',
              style: TextStyle(color: palette.muted, fontSize: 11),
            ),
          ],
        ],
      ),
    );
  }
}

String _formatProbeTime(DateTime value) {
  String two(int part) => part.toString().padLeft(2, '0');
  return '${value.year}.${two(value.month)}.${two(value.day)} '
      '${two(value.hour)}:${two(value.minute)}';
}

String _orderCheckLabel(String code) => switch (code) {
  'ACCOUNT_SWITCH' => 'KB 계좌 조회',
  'ORDER_PRECHECK_SWITCH' => '주문 사전검증',
  'LIVE_ORDER_SWITCH' => '실주문 별도 스위치',
  'CREDENTIALS' => 'KB API 인증',
  'ACCOUNT_NUMBER' => '계좌번호',
  'HTTPS_ENDPOINT' => 'KB HTTPS 연결',
  'ORDER_IP' => '운영 주문 IP',
  'ORDER_MAC' => '운영 주문 MAC',
  'SUBMISSION_TRANSPORT' => '실주문 전송 연결',
  _ => code,
};

class _ProviderCard extends StatelessWidget {
  const _ProviderCard({
    required this.provider,
    required this.marketDataPriority,
  });

  final ProviderSetting provider;
  final int marketDataPriority;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final chips = [
      if (provider.marketDataEnabled) '시세',
      if (provider.accountEnabled) '계좌',
      if (provider.orderEnabled) '주문',
      if (provider.newsEnabled) '뉴스',
      if (provider.disclosureEnabled) '공시',
    ];
    final enabled =
        provider.marketDataEnabled ||
        provider.accountEnabled ||
        provider.orderEnabled ||
        provider.newsEnabled ||
        provider.disclosureEnabled;
    final statusLabel = !enabled
        ? '꺼짐'
        : provider.configured
        ? '사용 가능'
        : '설정 필요';

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _ProviderIcon(code: provider.code),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      provider.displayName,
                      style: TextStyle(
                        color: palette.text,
                        fontSize: 16,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      provider.roleDescription,
                      style: TextStyle(
                        color: palette.muted,
                        fontSize: 12,
                        height: 1.3,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              StatusChip(
                label: statusLabel,
                gradient: enabled && provider.configured
                    ? AppGradients.main
                    : null,
              ),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (chips.isEmpty)
                const _RoleChip(label: '대기')
              else
                ...chips.map((chip) => _RoleChip(label: chip)),
              if (provider.marketDataEnabled && marketDataPriority >= 0)
                _RoleChip(label: '시세 ${marketDataPriority + 1}순위'),
              if (!provider.orderEnabled && provider.code == 'KB')
                const _RoleChip(label: '주문 잠금'),
            ],
          ),
          if (provider.missingRequiredSettings.isNotEmpty) ...[
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.info_outline_rounded,
                  color: palette.muted,
                  size: 16,
                ),
                const SizedBox(width: 7),
                Expanded(
                  child: Text(
                    '누락: ${provider.missingRequiredSettings.join(' · ')}',
                    style: TextStyle(
                      color: palette.muted,
                      fontSize: 11,
                      height: 1.35,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _ProviderIcon extends StatelessWidget {
  const _ProviderIcon({required this.code});

  final String code;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final icon = switch (code) {
      'KB' => Icons.account_balance_rounded,
      'KIS' => Icons.show_chart_rounded,
      'TOSS' => Icons.candlestick_chart_rounded,
      'NAVER_NEWS' => Icons.newspaper_rounded,
      'OPEN_DART' => Icons.description_rounded,
      _ => Icons.hub_rounded,
    };

    return Container(
      width: 38,
      height: 38,
      decoration: BoxDecoration(
        color: palette.softSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: palette.border),
      ),
      child: Icon(icon, color: AppTheme.main, size: 21),
    );
  }
}

class _MarketFallbackCard extends StatelessWidget {
  const _MarketFallbackCard({required this.settings});

  final ProviderSettingsSnapshot settings;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final names = <String, String>{
      for (final provider in settings.providers)
        provider.code: provider.displayName,
    };
    final order = settings.marketDataFallbackOrder
        .map((code) => names[code] ?? code)
        .followedBy(const ['등록 매수가'])
        .join(' → ');

    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.alt_route_rounded, color: AppTheme.main),
              const SizedBox(width: 8),
              Text(
                '시세 fallback',
                style: TextStyle(
                  color: palette.text,
                  fontSize: 15,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            order,
            style: TextStyle(
              color: palette.text,
              fontSize: 12,
              height: 1.35,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
          if (settings.marketDataFallbackDescription.isNotEmpty) ...[
            const SizedBox(height: 7),
            Text(
              settings.marketDataFallbackDescription,
              style: TextStyle(
                color: palette.muted,
                fontSize: 11,
                height: 1.35,
                fontWeight: FontWeight.w700,
                letterSpacing: 0,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _RoleChip extends StatelessWidget {
  const _RoleChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: palette.softSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: palette.border),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: palette.text,
          fontSize: 11,
          fontWeight: FontWeight.w900,
          letterSpacing: 0,
        ),
      ),
    );
  }
}

class _KbAccountSection extends StatefulWidget {
  const _KbAccountSection({required this.provider, required this.repository});

  final ProviderSetting provider;
  final KbAccountRepository repository;

  @override
  State<_KbAccountSection> createState() => _KbAccountSectionState();
}

class _KbAccountSectionState extends State<_KbAccountSection> {
  Future<KbAccountSnapshot>? _future;

  @override
  void initState() {
    super.initState();
    if (_shouldFetch) {
      _future = widget.repository.fetchSnapshot();
    }
  }

  @override
  void didUpdateWidget(covariant _KbAccountSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_shouldFetch && oldWidget.repository != widget.repository) {
      _future = widget.repository.fetchSnapshot();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.provider.accountEnabled || !widget.provider.configured) {
      return const _KbAccountDisabledCard();
    }

    final future = _future ??= widget.repository.fetchSnapshot();
    return FutureBuilder<KbAccountSnapshot>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _KbAccountHeader(statusLabel: '조회 중'),
                SizedBox(height: 14),
                Center(child: CircularProgressIndicator()),
              ],
            ),
          );
        }

        if (snapshot.hasError || !snapshot.hasData) {
          return _KbAccountErrorCard(
            message: snapshot.error.toString(),
            onRetry: _reload,
          );
        }

        return _KbAccountLoadedCard(snapshot: snapshot.data!, onRetry: _reload);
      },
    );
  }

  void _reload() {
    setState(() {
      _future = widget.repository.fetchSnapshot();
    });
  }

  bool get _shouldFetch {
    return widget.provider.accountEnabled && widget.provider.configured;
  }
}

class _KbAccountDisabledCard extends StatelessWidget {
  const _KbAccountDisabledCard();

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      soft: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _KbAccountHeader(statusLabel: '대기'),
          const SizedBox(height: 10),
          Text(
            'KB 계좌 조회를 보려면 백엔드 .env.dev에서 KB 계좌 연동을 켜고 App Key/App Secret을 설정해 주세요.',
            style: TextStyle(
              color: palette.muted,
              fontSize: 12,
              height: 1.35,
              fontWeight: FontWeight.w700,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class _KbAccountErrorCard extends StatelessWidget {
  const _KbAccountErrorCard({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _KbAccountHeader(statusLabel: '실패'),
          const SizedBox(height: 10),
          Text(
            message,
            style: TextStyle(
              color: palette.text,
              fontSize: 12,
              height: 1.35,
              fontWeight: FontWeight.w700,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('KB 계좌 다시 조회'),
            ),
          ),
        ],
      ),
    );
  }
}

class _KbAccountLoadedCard extends StatelessWidget {
  const _KbAccountLoadedCard({required this.snapshot, required this.onRetry});

  final KbAccountSnapshot snapshot;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final holdings = snapshot.holdings.items;
    final settlementItems = snapshot.settlementBalance.items;
    final settlement = snapshot.settlementBalance.summary;
    final reportedSettlementCount = settlement.reportedItemCount;
    final execution = snapshot.executionBalance.summary;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(child: _KbAccountHeader(statusLabel: '조회 성공')),
              IconButton(
                onPressed: onRetry,
                tooltip: 'KB 계좌 다시 조회',
                icon: const Icon(Icons.refresh_rounded),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _KbMetricTile(label: '보유 주식', value: '${holdings.length}종목'),
              _KbMetricTile(
                label: '결제 예수금',
                value: '${formatCurrency(settlement.cashDeposit)}원',
              ),
              _KbMetricTile(
                label: '체결 순자산',
                value: '${formatCurrency(execution.netAssetValuationAmount)}원',
              ),
              _KbMetricTile(
                label: '체결 손익',
                value: formatSignedPercent(execution.totalYieldRate),
              ),
            ],
          ),
          const SizedBox(height: 14),
          _KbBalanceLine(
            label: '결제기준 평가금액',
            value: '${formatCurrency(settlement.totalValuationAmount)}원',
          ),
          const SizedBox(height: 8),
          _KbBalanceLine(
            label: '체결기준 평가손익',
            value:
                '${formatCurrency(execution.totalProfitAmount)}원 '
                '(${formatSignedPercent(execution.totalYieldRate)})',
          ),
          if (reportedSettlementCount != null &&
              reportedSettlementCount != settlementItems.length) ...[
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.warning_amber_rounded, size: 16),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'KB 결제 잔고 보고 $reportedSettlementCount건 · 현재 응답 ${settlementItems.length}건: 건수 확인 필요',
                    style: TextStyle(
                      color: AppPalette.of(context).text,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),
          ],
          if (holdings.isNotEmpty) ...[
            const SizedBox(height: 14),
            Text(
              '보유 주식 평가금액 중 비중',
              style: TextStyle(
                color: AppPalette.of(context).muted,
                fontSize: 11,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            for (final holding in holdings.take(3)) ...[
              _KbHoldingLine(
                holding: holding,
                hasValuation:
                    snapshot.holdings.summary.totalValuationAmount > 0,
              ),
              const SizedBox(height: 8),
            ],
          ],
          if (holdings.isNotEmpty || settlementItems.isNotEmpty) ...[
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: () => showDialog<void>(
                  context: context,
                  builder: (_) => KbHoldingsDetailDialog(snapshot: snapshot),
                ),
                icon: const Icon(Icons.list_alt_rounded),
                label: Text(
                  settlementItems.isNotEmpty
                      ? '계좌 잔고 상세 (${settlementItems.length})'
                      : '전체 보유 종목 (${holdings.length})',
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _KbAccountHeader extends StatelessWidget {
  const _KbAccountHeader({required this.statusLabel});

  final String statusLabel;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Row(
      children: [
        const Icon(Icons.account_balance_wallet_rounded, color: AppTheme.main),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            'KB 계좌 조회',
            style: TextStyle(
              color: palette.text,
              fontSize: 15,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
        StatusChip(label: statusLabel),
      ],
    );
  }
}

class _KbMetricTile extends StatelessWidget {
  const _KbMetricTile({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Container(
      width: 148,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: palette.softSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: palette.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              color: palette.muted,
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 5),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: TextStyle(
                color: palette.text,
                fontSize: 14,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _KbBalanceLine extends StatelessWidget {
  const _KbBalanceLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              color: palette.muted,
              fontSize: 12,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ),
        Text(
          value,
          style: TextStyle(
            color: palette.text,
            fontSize: 12,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
      ],
    );
  }
}

class _KbHoldingLine extends StatelessWidget {
  const _KbHoldingLine({required this.holding, required this.hasValuation});

  final KbHoldingItem holding;
  final bool hasValuation;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  holding.stockName.isEmpty
                      ? holding.stockCode
                      : holding.stockName,
                  style: TextStyle(
                    color: palette.text,
                    fontSize: 13,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  '${holding.stockCode} · ${holding.quantity.toStringAsFixed(0)}주',
                  style: TextStyle(
                    color: palette.muted,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${formatCurrency(holding.valuationAmount)}원',
                style: TextStyle(
                  color: palette.text,
                  fontSize: 12,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
              Text(
                hasValuation && holding.weightRate != null
                    ? '${holding.weightRate!.toStringAsFixed(1)}%'
                    : '비중 산정 불가',
                style: TextStyle(
                  color: palette.muted,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SettingLine extends StatelessWidget {
  const _SettingLine({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Row(
      children: [
        Icon(icon, size: 18, color: AppTheme.main),
        const SizedBox(width: 9),
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              color: palette.muted,
              fontSize: 12,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ),
        Text(
          value,
          style: TextStyle(
            color: palette.text,
            fontSize: 12,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
          ),
        ),
      ],
    );
  }
}

class _SettingsErrorState extends StatelessWidget {
  const _SettingsErrorState({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.settings_suggest_rounded, color: AppTheme.sub),
            const SizedBox(height: 10),
            Text(
              '설정을 불러오지 못했습니다',
              style: TextStyle(
                color: palette.text,
                fontSize: 17,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('다시 시도'),
            ),
          ],
        ),
      ),
    );
  }
}
