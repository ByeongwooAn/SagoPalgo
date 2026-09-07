from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs"
PDF_PATH = OUT_DIR / "sagopalgo_development_roadmap.pdf"

MAIN = colors.HexColor("#8d17c6")
SUB = colors.HexColor("#d44b76")
POINT = colors.HexColor("#f3a411")
INK = colors.HexColor("#16111f")
MUTED = colors.HexColor("#5f5968")
BLUE = colors.HexColor("#2E74B5")
DARK_BLUE = colors.HexColor("#1F4D78")
BORDER = colors.HexColor("#d9dee8")
FILL = colors.HexColor("#eef3f8")
SOFT_FILL = colors.HexColor("#f7f2fb")
POINT_FILL = colors.HexColor("#fff4df")


def register_fonts() -> str:
    candidates = [
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/malgunbd.ttf"),
        Path("C:/Windows/Fonts/NanumGothic.ttf"),
    ]
    regular = next((path for path in candidates if path.exists()), None)
    if regular is None:
        return "Helvetica"
    pdfmetrics.registerFont(TTFont("Korean", str(regular)))
    bold_path = Path("C:/Windows/Fonts/malgunbd.ttf")
    if bold_path.exists():
        pdfmetrics.registerFont(TTFont("Korean-Bold", str(bold_path)))
    else:
        pdfmetrics.registerFont(TTFont("Korean-Bold", str(regular)))
    return "Korean"


FONT = register_fonts()
BOLD_FONT = "Korean-Bold" if FONT == "Korean" else "Helvetica-Bold"


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName=BOLD_FONT,
            fontSize=27,
            leading=34,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=7,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName=FONT,
            fontSize=12.5,
            leading=18,
            textColor=MUTED,
            spaceAfter=18,
        ),
        "kicker": ParagraphStyle(
            "Kicker",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=10,
            leading=13,
            textColor=POINT,
            spaceAfter=7,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName=BOLD_FONT,
            fontSize=16,
            leading=21,
            textColor=BLUE,
            spaceBefore=16,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=BOLD_FONT,
            fontSize=13,
            leading=17,
            textColor=BLUE,
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=10.2,
            leading=14.5,
            textColor=INK,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=8.8,
            leading=12,
            textColor=INK,
            spaceAfter=3,
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            parent=base["BodyText"],
            fontName=BOLD_FONT,
            fontSize=8.8,
            leading=11.5,
            textColor=colors.HexColor("#1f2937"),
            alignment=TA_CENTER,
        ),
        "table": ParagraphStyle(
            "Table",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=8.5,
            leading=11.3,
            textColor=INK,
        ),
        "callout_title": ParagraphStyle(
            "CalloutTitle",
            parent=base["BodyText"],
            fontName=BOLD_FONT,
            fontSize=10.3,
            leading=13,
            textColor=MAIN,
            spaceAfter=4,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=9.4,
            leading=13,
            textColor=INK,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=9.7,
            leading=13.4,
            textColor=INK,
            leftIndent=14,
            firstLineIndent=0,
            spaceAfter=3,
        ),
    }


S = styles()


def p(text: str, style="body") -> Paragraph:
    return Paragraph(text, S[style])


def bullet_list(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(item, "bullet"), leftIndent=10) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=14,
        bulletFontName=FONT,
        bulletFontSize=7,
    )


def number_list(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(item, "bullet"), leftIndent=10) for item in items],
        bulletType="1",
        leftIndent=16,
        bulletFontName=FONT,
        bulletFontSize=9,
    )


def table(headers: list[str], rows: list[list[str]], widths: list[float], header_fill=FILL):
    data = [[p(h, "table_head") for h in headers]]
    data.extend([[p(cell, "table") for cell in row] for row in rows])
    t = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_fill),
                ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def callout(title: str, body: str, fill=SOFT_FILL, accent=MAIN):
    title_style = ParagraphStyle(
        "DynamicCalloutTitle",
        parent=S["callout_title"],
        textColor=accent,
    )
    body_table = Table(
        [[Paragraph(title, title_style), p(body, "callout")]],
        colWidths=[1.15 * inch, 5.05 * inch],
        hAlign="LEFT",
    )
    body_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return body_table


def header_footer(canvas, doc):
    canvas.saveState()
    width, height = letter
    canvas.setFont(FONT, 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(inch, height - 0.56 * inch, "사고팔고 개발 실행계획서")
    canvas.setStrokeColor(BORDER)
    canvas.line(inch, height - 0.64 * inch, width - inch, height - 0.64 * inch)
    canvas.drawRightString(width - inch, 0.55 * inch, f"{doc.page}")
    canvas.restoreState()


def build_story():
    story = []
    story.append(p("개발 실행계획서", "kicker"))
    story.append(p("사고팔고 개발 로드맵", "title"))
    story.append(p("AI 기반 반자동 주식 투자 어시스턴트 시스템 구축 단계", "subtitle"))
    story.append(
        table(
            ["항목", "내용"],
            [
                ["기준 문서", "사고팔고 기획서"],
                ["적용 색상", "#8d17c6 메인 / #d44b76 서브 / #f3a411 포인트"],
                ["핵심 방향", "자동매매 수익 보장이 아니라 확률 기반 의사결정 보조"],
                ["개발 원칙", "리스크 관리, 점수 기준 명확화, 단계적 자동화, 검증 가능한 AI"],
            ],
            [1.35 * inch, 4.85 * inch],
            SOFT_FILL,
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        callout(
            "요약",
            "가장 먼저 Flutter 앱 UI, Spring Boot 인증/사용자 데이터, Python 분석 서버 골격을 연결한 뒤 RSI·뉴스 분석·알림까지 MVP로 완성한다. 이후 점수 시스템, 보유 종목 추적, 백테스트, 반자동 주문 순서로 확장한다.",
            POINT_FILL,
            POINT,
        )
    )

    story.append(p("1. 개발 방향", "h1"))
    story.append(
        p(
            "사고팔고는 AI가 자동으로 돈을 벌어주는 앱이 아니라, 시장·기술지표·뉴스·보유 종목 상태를 종합하여 사용자의 투자 판단을 보조하는 서비스로 개발해야 한다."
        )
    )
    story.append(
        bullet_list(
            [
                "초기 목표는 주문 자동화가 아니라 분석 결과를 신뢰할 수 있게 보여주는 MVP이다.",
                "추천은 반드시 점수와 근거를 함께 제공하여 AI 환각과 설명 불투명성을 줄인다.",
                "수익률보다 리스크 관리가 우선이며, 손절·익절·종목별 투자 비율을 기본 정책으로 둔다.",
                "Spring Boot는 인증, 사용자 데이터, 알림, AI 서버 연동의 중앙 허브 역할을 맡는다.",
                "Python AI 서버는 데이터 수집, 지표 계산, 뉴스 감성 분석, 점수 계산을 담당한다.",
            ]
        )
    )

    story.append(p("2. 전체 개발 단계 요약", "h1"))
    story.append(
        table(
            ["단계", "목표", "주요 작업", "완료 기준"],
            [
                ["0단계 기반 구축", "개발 환경과 공통 구조 준비", "Flutter/Spring/Python 프로젝트 정리, DB 설계, API 계약, 배포 방식 결정", "앱-API-AI 서버가 샘플 데이터로 연결됨"],
                ["1단계 MVP", "사용자가 추천 신호를 받을 수 있는 최소 제품", "로그인, 자본금, 관심 종목, RSI 계산, 뉴스 분석, FCM 알림", "관심 종목에 대해 매수 후보 알림을 받을 수 있음"],
                ["2단계 점수·보유 종목", "추천 품질과 투자 추적 기능 강화", "점수 시스템, 보유 종목, 손익 계산, 매도 추천, 리스크 규칙", "매수/매도 판단 근거와 수익률 추적이 앱에서 확인됨"],
                ["3단계 백테스트", "전략 검증과 점수 기준 개선", "과거 데이터 분석, 승률/손익/최대손실 계산, 전략 파라미터 최적화", "추천 전략의 과거 성과 리포트를 생성할 수 있음"],
                ["4단계 반자동 주문", "사용자 승인 기반 주문 연동", "한국투자/키움 API 연동, 주문 전 확인, 실패/취소 처리, 감사 로그", "사용자 확인 후 주문 요청이 안전하게 실행됨"],
            ],
            [1.0 * inch, 1.3 * inch, 2.45 * inch, 1.45 * inch],
        )
    )

    story.append(PageBreak())
    story.append(p("3. 0단계: 기반 구축", "h1"))
    story.append(
        callout(
            "목표",
            "기능 개발보다 먼저 팀이 같은 구조로 개발할 수 있게 만드는 준비 단계이다. 여기서 API 계약과 데이터 모델을 정하지 않으면 이후 AI 서버, 앱, 백엔드가 서로 어긋나기 쉽다.",
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        table(
            ["순서", "작업", "산출물", "주의점"],
            [
                ["1", "프로젝트 구조 정리", "Front Flutter, Back Spring, AI Python 서버 폴더/실행법", "각 서버의 실행 포트와 env 규칙 통일"],
                ["2", "공통 도메인 정의", "User, Capital, Watchlist, Holding, Recommendation, Alert 모델", "앱 화면명과 API 필드명을 맞춤"],
                ["3", "DB 초안 설계", "users, capital, watchlist, holdings, alerts, recommendations 테이블", "투자 기록은 수정 이력 추적 가능하게 설계"],
                ["4", "API 계약 작성", "OpenAPI 또는 Markdown API 명세", "AI 서버 응답 형식도 먼저 고정"],
                ["5", "샘플 데이터 연결", "앱 대시보드에 API 샘플 응답 표시", "실데이터 전에도 화면 흐름 검증"],
            ],
            [0.45 * inch, 1.45 * inch, 2.45 * inch, 1.85 * inch],
        )
    )

    story.append(PageBreak())
    story.append(p("4. 1단계 MVP: 로그인·관심종목·RSI·뉴스·알림", "h1"))
    story.append(p("MVP는 사용자가 관심 종목을 등록하고, 시스템이 기초 분석 결과를 알림으로 전달하는 흐름까지를 목표로 한다."))
    story.append(
        number_list(
            [
                "회원가입/로그인: Spring Security + JWT로 인증을 구현하고 Flutter에서 토큰 저장 및 자동 로그인 흐름을 만든다.",
                "자본금 설정: 사용자가 투자 가능 금액을 입력하고, 종목당 권장 투자 범위를 계산해 보여준다.",
                "관심 종목 관리: 종목 코드, 시장, 별칭, 알림 여부를 저장하고 앱에서 추가/삭제/조회한다.",
                "RSI 계산: Python 서버에서 최근 가격 데이터를 기반으로 RSI를 계산하고 Spring API가 앱에 전달한다.",
                "뉴스 분석: 뉴스 수집, 텍스트 정제, LLM 감성 판단, 긍정/부정 점수화를 분리해 구현한다.",
                "알림 발송: 점수 또는 조건이 임계값을 넘으면 Firebase FCM으로 매수 후보 알림을 발송한다.",
            ]
        )
    )
    story.append(
        table(
            ["구분", "구현 범위", "검증 방법"],
            [
                ["앱", "로그인, 자본금 입력, 관심 종목 목록, 알림 목록, 추천 상세 화면", "에뮬레이터에서 주요 화면 이동과 테마 전환 확인"],
                ["백엔드", "JWT 인증, 사용자/관심종목/자본금 API, 알림 API", "Postman 또는 통합 테스트로 200/401/403 케이스 검증"],
                ["AI 서버", "RSI 계산, 뉴스 감성 분석 Mock 또는 실제 호출", "삼성전자 샘플 데이터로 동일 입력 시 동일 점수 반환"],
                ["알림", "FCM 토큰 저장, 테스트 푸시, 추천 알림 발송", "실제 Android 기기 또는 에뮬레이터에서 수신 확인"],
            ],
            [0.85 * inch, 3.25 * inch, 2.1 * inch],
        )
    )

    story.append(PageBreak())
    story.append(p("5. 2단계: 점수 시스템과 보유 종목 추적", "h1"))
    story.append(p("2단계부터는 추천의 품질을 결정하는 핵심 로직을 만든다. 점수는 AI 설명보다 우선되는 기준이며, 백테스트와 자동화의 기반이 된다."))
    story.append(
        table(
            ["조건", "기본 점수", "구현 메모"],
            [
                ["RSI 과매도 탈출", "20", "단순 RSI < 30뿐 아니라 회복 여부를 별도 조건으로 둔다."],
                ["MACD 골든크로스", "20", "교차 발생일과 신호선 간격을 함께 저장한다."],
                ["거래량 증가", "25", "최근 평균 대비 2배 이상 증가 여부를 기준으로 시작한다."],
                ["뉴스 긍정", "15", "종목 뉴스와 업종 뉴스를 구분해 가중치를 조정한다."],
                ["외국인 순매수", "10", "초기에는 수집 가능할 때만 옵션 조건으로 둔다."],
                ["시장 강세", "10", "코스피/나스닥/업종 지수를 별도 시장 점수로 계산한다."],
            ],
            [2.05 * inch, 0.85 * inch, 3.3 * inch],
        )
    )
    story.append(
        bullet_list(
            [
                "80점 이상: 강한 매수, 60~79점: 관심, 40~59점: 관망, 40점 미만: 위험으로 표시한다.",
                "보유 종목은 매수가, 수량, 매수일, 손절 기준, 익절 기준을 반드시 저장한다.",
                "현재가 갱신 후 수익률을 계산하고 손절·익절·추세 붕괴·뉴스 악화 조건을 매도 추천에 반영한다.",
                "앱은 점수만 보여주지 말고 RSI, 거래량, 뉴스 등 점수가 생긴 이유를 함께 보여줘야 한다.",
            ]
        )
    )

    story.append(p("6. 3단계: 백테스트와 전략 최적화", "h1"))
    story.append(p("백테스트는 ‘이 전략이 과거에도 유효했는가’를 확인하기 위한 단계이다. 추천 자동화 전에 반드시 수행해야 한다."))
    story.append(
        table(
            ["작업", "구체적 내용", "결과물"],
            [
                ["데이터 기간 설정", "초기 1년 데이터를 기준으로 시작하고, 이후 3개월/1년/5년 구간을 비교", "기간별 성과 비교 리포트"],
                ["전략 재현", "RSI, MACD, 거래량, 뉴스 점수 조건을 과거 시점 기준으로 재현", "전략 실행 로그"],
                ["성과 계산", "승률, 평균 수익률, 최대 손실, 손익비, 연속 손실 횟수 계산", "백테스트 요약 지표"],
                ["파라미터 조정", "RSI 기준, 거래량 배수, 점수 임계값을 바꿔 성능 비교", "추천 기준 개선안"],
            ],
            [1.45 * inch, 3.65 * inch, 1.1 * inch],
        )
    )
    story.append(
        callout(
            "주의",
            "뉴스 감성 분석은 과거 뉴스 시점과 실제 공개 시간을 기준으로 해야 한다. 미래 정보를 사용하면 백테스트 결과가 왜곡된다.",
            POINT_FILL,
            SUB,
        )
    )

    story.append(PageBreak())
    story.append(p("7. 4단계: 반자동 주문", "h1"))
    story.append(p("반자동 주문은 마지막 단계로 둔다. 분석과 추천이 충분히 검증되기 전에는 주문 API를 연결하지 않는 것이 안전하다."))
    story.append(
        bullet_list(
            [
                "주문은 사용자의 명시적 확인 후에만 실행한다.",
                "주문 전 예상 손실, 종목당 투자 비율, 손절/익절 기준을 다시 보여준다.",
                "한국투자 API 또는 키움 API 연동은 샌드박스/모의투자 환경에서 먼저 검증한다.",
                "주문 요청, 성공, 실패, 취소, 재시도는 모두 감사 로그로 남긴다.",
                "자동 주문 전환은 별도 설정으로 잠그고 기본값은 비활성화한다.",
            ]
        )
    )

    story.append(p("8. 추천 일정", "h1"))
    story.append(
        table(
            ["기간", "핵심 목표", "주요 산출물"],
            [
                ["1주차", "프로젝트 기반 구축", "API 명세, DB 초안, Flutter UI 골격, Spring/Python 서버 실행"],
                ["2~3주차", "인증·관심종목·자본금", "JWT 로그인, 관심 종목 CRUD, 자본금 설정 화면"],
                ["4~5주차", "RSI·뉴스 분석 MVP", "RSI 계산 API, 뉴스 감성 분석 API, 추천 후보 응답"],
                ["6주차", "알림 MVP", "FCM 토큰 저장, 매수 추천 푸시 알림, 알림 히스토리"],
                ["7~8주차", "점수 시스템", "점수 계산 엔진, 추천 상세 근거, 점수 상태 분류"],
                ["9~10주차", "보유 종목·매도 추천", "손익 계산, 손절/익절 알림, 매도 추천 화면"],
                ["11~12주차", "백테스트 1차", "과거 1년 데이터 기반 전략 검증 리포트"],
                ["이후", "반자동 주문", "모의투자 주문 연동, 승인 화면, 주문 로그"],
            ],
            [0.9 * inch, 1.75 * inch, 3.55 * inch],
        )
    )

    story.append(PageBreak())
    story.append(p("9. 우선 구현할 API와 DB", "h1"))
    story.append(
        table(
            ["영역", "API 예시", "DB/저장 대상"],
            [
                ["인증", "POST /auth/signup, POST /auth/login, POST /auth/refresh", "users, refresh_tokens"],
                ["자본금", "GET/PUT /capital", "user_capital"],
                ["관심 종목", "GET/POST/DELETE /watchlist", "watchlist"],
                ["추천", "GET /recommendations, GET /recommendations/{id}", "recommendations, recommendation_reasons"],
                ["보유 종목", "GET/POST/PUT /holdings", "holdings, trade_records"],
                ["알림", "POST /devices/fcm-token, GET /alerts", "device_tokens, alerts"],
                ["AI 연동", "POST /ai/analyze-stock, POST /ai/analyze-news", "analysis_snapshots"],
            ],
            [0.95 * inch, 3.4 * inch, 1.85 * inch],
        )
    )

    story.append(p("10. 완료 기준", "h1"))
    story.append(
        bullet_list(
            [
                "앱: Android 기준으로 로그인부터 추천 상세, 보유 종목, 알림까지 끊김 없이 이동된다.",
                "백엔드: 인증이 필요한 API는 JWT 없이 호출할 수 없고, 사용자별 데이터가 분리된다.",
                "AI 서버: 동일 데이터에 대해 재현 가능한 점수와 추천 사유를 반환한다.",
                "알림: 추천 조건 충족 시 FCM 알림이 발송되고 앱 내 알림 기록에 저장된다.",
                "리스크: 종목당 투자 비율, 손절 기준, 1회 거래 손실 제한이 추천 화면에 반영된다.",
                "운영: 주요 오류는 로그로 추적 가능하고, 외부 API 실패 시 사용자에게 안전한 메시지를 보여준다.",
            ]
        )
    )

    story.append(p("11. 지금 바로 할 다음 작업", "h1"))
    story.append(
        table(
            ["우선순위", "작업", "담당 영역"],
            [
                ["P0", "현재 Flutter UI를 실제 API 연동 가능한 화면 구조로 분리", "Frontend"],
                ["P0", "Spring Boot 프로젝트 생성 및 JWT 인증 골격 구현", "Backend"],
                ["P0", "users, user_capital, watchlist 기본 테이블 설계", "Backend/DB"],
                ["P1", "Python AI 서버 FastAPI 또는 Flask 골격 생성", "AI Server"],
                ["P1", "삼성전자 샘플 데이터로 RSI 계산 API 구현", "AI Server"],
                ["P1", "추천 응답 JSON 계약 정의 후 앱에 Mock 연동", "All"],
                ["P2", "뉴스 수집 소스 선정 및 감성 분석 프롬프트/스키마 설계", "AI Server"],
                ["P2", "FCM 프로젝트 설정 및 테스트 푸시 검증", "Backend/Frontend"],
            ],
            [0.8 * inch, 4.15 * inch, 1.25 * inch],
        )
    )
    return story


def build_pdf():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=0.86 * inch,
        bottomMargin=0.82 * inch,
        title="사고팔고 개발 로드맵",
        author="Codex",
    )
    doc.build(build_story(), onFirstPage=header_footer, onLaterPages=header_footer)
    print(PDF_PATH)


if __name__ == "__main__":
    build_pdf()
