import 'package:flutter_test/flutter_test.dart';
import 'package:app_version/models/app_alert.dart';

void main() {
  test('뉴스 알림의 이벤트 메타데이터와 화면 유형을 변환한다', () {
    final alert = AppAlert.fromJson({
      'alertId': 21,
      'eventType': 'NEWS',
      'stockCode': '005930',
      'title': '삼성전자 새 뉴스',
      'body': '실적 개선 소식',
      'timeLabel': '방금 전',
      'type': 'NEWS',
      'read': false,
    });

    expect(alert.eventType, 'NEWS');
    expect(alert.stockCode, '005930');
    expect(alert.type, AppAlertType.news);
    expect(alert.copyWith(isRead: true).eventType, 'NEWS');
  });

  test('가격과 공시 및 포트폴리오 알림을 각각의 화면 유형으로 변환한다', () {
    AppAlert parse(String type) => AppAlert.fromJson({
      'title': '이벤트',
      'body': '내용',
      'timeLabel': '1분 전',
      'type': type,
    });

    expect(parse('PRICE').type, AppAlertType.price);
    expect(parse('DISCLOSURE').type, AppAlertType.disclosure);
    expect(parse('PORTFOLIO').type, AppAlertType.portfolio);
  });
}
