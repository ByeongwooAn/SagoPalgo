import 'package:flutter/material.dart';

import '../models/provider_setting.dart';
import '../theme/app_theme.dart';
import '../widgets/app_card.dart';
import '../widgets/section_header.dart';
import '../widgets/status_chip.dart';
import 'dashboard_screen.dart';

/// 개인용 프로그램 설정 화면입니다.
class SettingsScreen extends StatelessWidget {
  /// 증권사 설정 Future와 재시도 콜백을 받습니다.
  const SettingsScreen({
    super.key,
    required this.providerSettingsFuture,
    required this.onRetry,
  });

  /// 백엔드에서 조회하는 증권사 설정 Future입니다.
  final Future<ProviderSettingsSnapshot> providerSettingsFuture;

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

        final providers = snapshot.data!.providers;

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
                  ],
                ),
              ),
              const SizedBox(height: 12),
              ...providers.map(
                (provider) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _ProviderCard(provider: provider),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _ProviderCard extends StatelessWidget {
  const _ProviderCard({required this.provider});

  final ProviderSetting provider;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    final chips = [
      if (provider.marketDataEnabled) '시세',
      if (provider.accountEnabled) '계좌',
      if (provider.orderEnabled) '주문',
    ];

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
                label: provider.configured ? '설정됨' : '미설정',
                gradient: provider.configured ? AppGradients.main : null,
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
              if (!provider.orderEnabled && provider.code == 'KB')
                const _RoleChip(label: '주문 잠금'),
            ],
          ),
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
      _ => Icons.candlestick_chart_rounded,
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
