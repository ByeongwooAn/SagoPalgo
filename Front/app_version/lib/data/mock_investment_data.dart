import '../models/app_alert.dart';
import '../models/holding.dart';
import '../models/investment_snapshot.dart';
import '../models/market_summary.dart';
import '../models/recommendation.dart';

/// 기획서에 나온 MVP 흐름을 앱에서 바로 확인하기 위한 Mock 데이터입니다.
///
/// 이 파일의 목적은 화면에 흩어진 하드코딩 값을 한곳으로 모으는 것입니다.
/// API가 준비되면 이 데이터는 삭제하거나 테스트 전용 fixture로 이동하면 됩니다.
const mockInvestmentSnapshot = InvestmentSnapshot(
  marketSummary: MarketSummary(
    availableCapital: 3000000,
    monthlyReturnRate: 3.8,
    recommendedPositionRange: '30~60만원',
    marketTrend: '강세',
    marketScore: 76,
    newsSentiment: '긍정',
    positiveNewsCount: 12,
    marketBars: [.42, .68, .54, .82, .61, .94],
  ),
  recommendation: InvestmentRecommendation(
    stockName: '삼성전자',
    stockCode: '005930',
    market: 'KOSPI',
    status: '강한 매수',
    score: 87,
    entryPrice: 72000,
    stopLossRate: -5,
    aiSummary:
        '시장 강세와 거래량 증가가 동시에 나타나 단기 관심 종목으로 분류됩니다. 전체 자산의 1~2% 손실 제한을 유지하세요.',
    reasons: [
      RecommendationReason(
        label: 'RSI',
        description: '과매도 구간에서 반등 신호가 확인되었습니다.',
        type: RecommendationReasonType.technical,
      ),
      RecommendationReason(
        label: 'MACD',
        description: '골든크로스 초기 구간으로 추세 전환 가능성이 있습니다.',
        type: RecommendationReasonType.trend,
      ),
      RecommendationReason(
        label: '뉴스',
        description: 'AI 반도체 수주 관련 긍정 감성이 증가했습니다.',
        type: RecommendationReasonType.news,
      ),
    ],
  ),
  portfolioSummary: PortfolioSummary(
    totalProfit: 128400,
    profitRate: 4.2,
    maxAllowedLoss: 60000,
    riskUsageRate: .42,
  ),
  holdings: [
    Holding(
      stockName: '삼성전자',
      stockCode: '005930',
      buyPrice: 69100,
      quantity: 12,
      profitRate: 9.0,
      status: '부분 익절',
    ),
    Holding(
      stockName: 'NAVER',
      stockCode: '035420',
      buyPrice: 181000,
      quantity: 4,
      profitRate: 2.1,
      status: '보유',
    ),
    Holding(
      stockName: '현대차',
      stockCode: '005380',
      buyPrice: 224000,
      quantity: 2,
      profitRate: -3.6,
      status: '손절 감시',
    ),
  ],
  alerts: [
    AppAlert(
      title: '삼성전자 매도 검토',
      body: '현재 수익률 +9%. 목표 수익 도달로 부분 익절을 추천합니다.',
      timeLabel: '방금 전',
      type: AppAlertType.sell,
    ),
    AppAlert(
      title: '관심 종목 신규 후보',
      body: 'RSI 과매도 탈출과 거래량 2.1배 증가가 동시에 감지되었습니다.',
      timeLabel: '3분 전',
      type: AppAlertType.candidate,
    ),
    AppAlert(
      title: '시장 흐름 업데이트',
      body: '코스피와 나스닥 지표가 모두 강세 구간으로 전환되었습니다.',
      timeLabel: '5분 전',
      type: AppAlertType.market,
    ),
  ],
);
