# Flutter Windows 앱

- 루트 공통 지침에 이 디렉터리의 규칙을 추가 적용한다.
- Windows 데스크톱을 우선하며 관련 화면·상태·Repository와 대응 테스트부터 읽는다.
- 기존 테마·레이아웃·문구 패턴을 따른다. 모바일·다른 플랫폼 변경은 영향이 있을 때만 수행한다.
- 앱에는 공개 접속 설정만 둔다. 서버 `.env`·Provider 키·계좌 비밀값을 asset에 넣지 않고 PIN은 기존 Credential Manager 방식을 유지한다.
- 화면 진입으로 외부 수집·주문을 자동 활성화하지 않는다. 변경 요청의 응답 유실·재시도 처리는 서버 계약과 대조한다.
- 명령은 이 폴더에서 실행한다. 개발 중 `flutter test test/<관련 파일>`로 확인한다.
- Dart 코드 변경 마무리에는 `flutter analyze`와 `flutter test`를 실행한다. 화면 변경은 관련 widget 테스트와 가능한 화면 확인을 수행한다.
- Windows 네이티브·플러그인·패키징 변경에는 `flutter build windows --release`와 필요한 실행 확인을 추가한다. 문구·Dart 수정마다 Windows 빌드를 반복하지 않는다.
