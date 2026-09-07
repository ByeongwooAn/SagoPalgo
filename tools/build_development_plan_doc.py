from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs"
DOCX_PATH = OUT_DIR / "sagopalgo_development_plan.docx"

MAIN = "8D17C6"
SUB = "D44B76"
POINT = "F3A411"
BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
MUTED = "666666"
BORDER = "D9DEE8"
FILL = "E8EEF5"
SOFT_FILL = "F7F4FA"
RISK_FILL = "FFF4E2"


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color: str = BORDER, size: str = "4") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right"):
        tag = f"w:{edge}"
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = tc_pr.first_child_found_in("w:tcMar")
    if mar is None:
        mar = OxmlElement("w:tcMar")
        tc_pr.append(mar)
    for side, value in (
        ("top", top),
        ("start", start),
        ("bottom", bottom),
        ("end", end),
    ):
        node = mar.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_cell_width(cell, width_dxa: int) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    width = tc_pr.first_child_found_in("w:tcW")
    if width is None:
        width = OxmlElement("w:tcW")
        tc_pr.append(width)
    width.set(qn("w:w"), str(width_dxa))
    width.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths_dxa: list[int]) -> None:
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths_dxa)))
    tbl_w.set(qn("w:type"), "dxa")

    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "120")
    tbl_ind.set(qn("w:type"), "dxa")

    tbl_grid = table._tbl.tblGrid
    for child in list(tbl_grid):
        tbl_grid.remove(child)
    for width in widths_dxa:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(width))
        tbl_grid.append(grid_col)

    for row in table.rows:
        for index, width in enumerate(widths_dxa):
            cell = row.cells[index]
            set_cell_width(cell, width)
            set_cell_margins(cell)
            set_cell_border(cell)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def set_run_font(run, size=None, bold=None, color=None, name="Malgun Gothic") -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:ascii"), name)
    run._element.rPr.rFonts.set(qn("w:hAnsi"), name)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def add_para(doc, text="", style=None, size=11, bold=False, color=None, after=6, before=0):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.25
    if text:
        run = p.add_run(text)
        set_run_font(run, size=size, bold=bold, color=color)
    return p


def add_heading(doc, text, level=1):
    style = f"Heading {level}"
    p = doc.add_paragraph(style=style)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    size = {1: 16, 2: 13, 3: 12}[level]
    color = BLUE if level in (1, 2) else DARK_BLUE
    set_run_font(run, size=size, bold=True, color=color)
    return p


def add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.25
        run = p.add_run(item)
        set_run_font(run, size=10.5)


def add_numbered(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.25
        run = p.add_run(item)
        set_run_font(run, size=10.5)


def add_callout(doc, title, body, fill=SOFT_FILL, accent=MAIN):
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [9360])
    cell = table.cell(0, 0)
    set_cell_shading(cell, fill)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(4)
    title_run = p.add_run(title)
    set_run_font(title_run, size=11, bold=True, color=accent)
    p2 = cell.add_paragraph()
    p2.paragraph_format.space_after = Pt(0)
    p2.paragraph_format.line_spacing = 1.25
    body_run = p2.add_run(body)
    set_run_font(body_run, size=10.5, color="222222")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_table(doc, headers, rows, widths, header_fill=FILL):
    table = doc.add_table(rows=1, cols=len(headers))
    set_table_geometry(table, widths)
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        set_cell_shading(cell, header_fill)
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(header)
        set_run_font(run, size=9.5, bold=True, color="1F2937")
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.18
            run = p.add_run(value)
            set_run_font(run, size=9.2, color="222222")
    set_table_geometry(table, widths)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return table


def configure_document(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Malgun Gothic"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    for style_name, size, color, before, after in [
        ("Heading 1", 16, BLUE, 18, 10),
        ("Heading 2", 13, BLUE, 14, 7),
        ("Heading 3", 12, DARK_BLUE, 10, 5),
    ]:
        style = styles[style_name]
        style.font.name = "Malgun Gothic"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.line_spacing = 1.25

    for style_name in ("List Bullet", "List Number"):
        style = styles[style_name]
        style.font.name = "Malgun Gothic"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
        style.font.size = Pt(10.5)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.25
        style.paragraph_format.left_indent = Inches(0.375)
        style.paragraph_format.first_line_indent = Inches(-0.188)

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = header.add_run("사고팔고 개발 실행계획서")
    set_run_font(run, size=9, bold=True, color=MUTED)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer.add_run("AI 기반 반자동 주식 투자 어시스턴트")
    set_run_font(run, size=9, color=MUTED)


def add_cover(doc: Document) -> None:
    add_para(doc, "개발 실행계획서", size=11, bold=True, color=POINT, after=8, before=8)
    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(6)
    run = title.add_run("사고팔고 개발 로드맵")
    set_run_font(run, size=27, bold=True, color="111827")

    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(16)
    run = subtitle.add_run("AI 기반 반자동 주식 투자 어시스턴트 시스템 구축 단계")
    set_run_font(run, size=13, bold=False, color=MUTED)

    add_table(
        doc,
        ["항목", "내용"],
        [
            ("기준 문서", "사고팔고 기획서"),
            ("적용 색상", "#8d17c6 메인 / #d44b76 서브 / #f3a411 포인트"),
            ("핵심 방향", "자동매매 수익 보장이 아니라 확률 기반 의사결정 보조"),
            ("개발 원칙", "리스크 관리, 점수 기준 명확화, 단계적 자동화, 검증 가능한 AI"),
        ],
        [2200, 7160],
        header_fill=SOFT_FILL,
    )

    add_callout(
        doc,
        "요약",
        "가장 먼저 Flutter 앱 UI, Spring Boot 인증/사용자 데이터, Python 분석 서버 골격을 연결한 뒤 RSI·뉴스 분석·알림까지 MVP로 완성한다. 이후 점수 시스템, 보유 종목 추적, 백테스트, 반자동 주문 순서로 확장한다.",
        fill=RISK_FILL,
        accent=POINT,
    )


def build_document() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = Document()
    configure_document(doc)
    add_cover(doc)

    add_heading(doc, "1. 개발 방향", 1)
    add_para(
        doc,
        "사고팔고는 AI가 자동으로 돈을 벌어주는 앱이 아니라, 시장·기술지표·뉴스·보유 종목 상태를 종합하여 사용자의 투자 판단을 보조하는 서비스로 개발해야 한다.",
    )
    add_bullets(
        doc,
        [
            "초기 목표는 주문 자동화가 아니라 분석 결과를 신뢰할 수 있게 보여주는 MVP이다.",
            "추천은 반드시 점수와 근거를 함께 제공하여 AI 환각과 설명 불투명성을 줄인다.",
            "수익률보다 리스크 관리가 우선이며, 손절·익절·종목별 투자 비율을 기본 정책으로 둔다.",
            "Spring Boot는 인증, 사용자 데이터, 알림, AI 서버 연동의 중앙 허브 역할을 맡는다.",
            "Python AI 서버는 데이터 수집, 지표 계산, 뉴스 감성 분석, 점수 계산을 담당한다.",
        ]
    )

    add_heading(doc, "2. 전체 개발 단계 요약", 1)
    add_table(
        doc,
        ["단계", "목표", "주요 작업", "완료 기준"],
        [
            (
                "0단계 기반 구축",
                "개발 환경과 공통 구조 준비",
                "Flutter/Spring/Python 프로젝트 정리, DB 설계, API 계약, 배포 방식 결정",
                "앱-API-AI 서버가 샘플 데이터로 연결됨",
            ),
            (
                "1단계 MVP",
                "사용자가 추천 신호를 받을 수 있는 최소 제품",
                "로그인, 자본금, 관심 종목, RSI 계산, 뉴스 분석, FCM 알림",
                "관심 종목에 대해 매수 후보 알림을 받을 수 있음",
            ),
            (
                "2단계 점수·보유 종목",
                "추천 품질과 투자 추적 기능 강화",
                "점수 시스템, 보유 종목, 손익 계산, 매도 추천, 리스크 규칙",
                "매수/매도 판단 근거와 수익률 추적이 앱에서 확인됨",
            ),
            (
                "3단계 백테스트",
                "전략 검증과 점수 기준 개선",
                "과거 데이터 분석, 승률/손익/최대손실 계산, 전략 파라미터 최적화",
                "추천 전략의 과거 성과 리포트를 생성할 수 있음",
            ),
            (
                "4단계 반자동 주문",
                "사용자 승인 기반 주문 연동",
                "한국투자/키움 API 연동, 주문 전 확인, 실패/취소 처리, 감사 로그",
                "사용자 확인 후 주문 요청이 안전하게 실행됨",
            ),
        ],
        [1450, 1900, 3650, 2360],
    )

    add_heading(doc, "3. 0단계: 기반 구축", 1)
    add_callout(
        doc,
        "목표",
        "이 단계는 기능 개발보다 먼저 팀이 같은 구조로 개발할 수 있게 만드는 준비 단계이다. 여기서 API 계약과 데이터 모델을 정하지 않으면 이후 AI 서버, 앱, 백엔드가 서로 어긋나기 쉽다.",
        fill=SOFT_FILL,
        accent=MAIN,
    )
    add_table(
        doc,
        ["순서", "작업", "산출물", "주의점"],
        [
            ("1", "프로젝트 구조 정리", "Front Flutter, Back Spring, AI Python 서버 폴더/실행법", "각 서버의 실행 포트와 env 규칙 통일"),
            ("2", "공통 도메인 정의", "User, Capital, Watchlist, Holding, Recommendation, Alert 모델", "앱 화면명과 API 필드명을 맞춤"),
            ("3", "DB 초안 설계", "users, capital, watchlist, holdings, alerts, recommendations 테이블", "투자 기록은 수정 이력 추적 가능하게 설계"),
            ("4", "API 계약 작성", "OpenAPI 또는 Markdown API 명세", "AI 서버 응답 형식도 먼저 고정"),
            ("5", "샘플 데이터 연결", "앱 대시보드에 API 샘플 응답 표시", "실데이터 전에도 화면 흐름 검증"),
        ],
        [900, 2200, 3100, 3160],
    )

    add_heading(doc, "4. 1단계 MVP: 로그인·관심종목·RSI·뉴스·알림", 1)
    add_para(doc, "MVP는 사용자가 관심 종목을 등록하고, 시스템이 기초 분석 결과를 알림으로 전달하는 흐름까지를 목표로 한다.")
    add_numbered(
        doc,
        [
            "회원가입/로그인: Spring Security + JWT로 인증을 구현하고 Flutter에서 토큰 저장 및 자동 로그인 흐름을 만든다.",
            "자본금 설정: 사용자가 투자 가능 금액을 입력하고, 종목당 권장 투자 범위를 계산해 보여준다.",
            "관심 종목 관리: 종목 코드, 시장, 별칭, 알림 여부를 저장하고 앱에서 추가/삭제/조회한다.",
            "RSI 계산: Python 서버에서 최근 가격 데이터를 기반으로 RSI를 계산하고 Spring API가 앱에 전달한다.",
            "뉴스 분석: 뉴스 수집, 텍스트 정제, LLM 감성 판단, 긍정/부정 점수화를 분리해 구현한다.",
            "알림 발송: 점수 또는 조건이 임계값을 넘으면 Firebase FCM으로 매수 후보 알림을 발송한다.",
        ]
    )
    add_table(
        doc,
        ["구분", "구현 범위", "검증 방법"],
        [
            ("앱", "로그인, 자본금 입력, 관심 종목 목록, 알림 목록, 추천 상세 화면", "에뮬레이터에서 주요 화면 이동과 테마 전환 확인"),
            ("백엔드", "JWT 인증, 사용자/관심종목/자본금 API, 알림 API", "Postman 또는 통합 테스트로 200/401/403 케이스 검증"),
            ("AI 서버", "RSI 계산, 뉴스 감성 분석 Mock 또는 실제 호출", "삼성전자 샘플 데이터로 동일 입력 시 동일 점수 반환"),
            ("알림", "FCM 토큰 저장, 테스트 푸시, 추천 알림 발송", "실제 Android 기기 또는 에뮬레이터에서 수신 확인"),
        ],
        [1450, 4800, 3110],
    )

    add_heading(doc, "5. 2단계: 점수 시스템과 보유 종목 추적", 1)
    add_para(doc, "2단계부터는 추천의 품질을 결정하는 핵심 로직을 만든다. 점수는 AI 설명보다 우선되는 기준이며, 백테스트와 자동화의 기반이 된다.")
    add_table(
        doc,
        ["조건", "기본 점수", "구현 메모"],
        [
            ("RSI 과매도 탈출", "20", "단순 RSI < 30뿐 아니라 회복 여부를 별도 조건으로 둔다."),
            ("MACD 골든크로스", "20", "교차 발생일과 신호선 간격을 함께 저장한다."),
            ("거래량 증가", "25", "최근 평균 대비 2배 이상 증가 여부를 기준으로 시작한다."),
            ("뉴스 긍정", "15", "종목 뉴스와 업종 뉴스를 구분해 가중치를 조정한다."),
            ("외국인 순매수", "10", "초기에는 수집 가능할 때만 옵션 조건으로 둔다."),
            ("시장 강세", "10", "코스피/나스닥/업종 지수를 별도 시장 점수로 계산한다."),
        ],
        [3000, 1300, 5060],
    )
    add_bullets(
        doc,
        [
            "80점 이상: 강한 매수, 60~79점: 관심, 40~59점: 관망, 40점 미만: 위험으로 표시한다.",
            "보유 종목은 매수가, 수량, 매수일, 손절 기준, 익절 기준을 반드시 저장한다.",
            "현재가 갱신 후 수익률을 계산하고 손절·익절·추세 붕괴·뉴스 악화 조건을 매도 추천에 반영한다.",
            "앱은 점수만 보여주지 말고 RSI, 거래량, 뉴스 등 점수가 생긴 이유를 함께 보여줘야 한다.",
        ]
    )

    add_heading(doc, "6. 3단계: 백테스트와 전략 최적화", 1)
    add_para(doc, "백테스트는 ‘이 전략이 과거에도 유효했는가’를 확인하기 위한 단계이다. 추천 자동화 전에 반드시 수행해야 한다.")
    add_table(
        doc,
        ["작업", "구체적 내용", "결과물"],
        [
            ("데이터 기간 설정", "초기 1년 데이터를 기준으로 시작하고, 이후 3개월/1년/5년 구간을 비교", "기간별 성과 비교 리포트"),
            ("전략 재현", "RSI, MACD, 거래량, 뉴스 점수 조건을 과거 시점 기준으로 재현", "전략 실행 로그"),
            ("성과 계산", "승률, 평균 수익률, 최대 손실, 손익비, 연속 손실 횟수 계산", "백테스트 요약 지표"),
            ("파라미터 조정", "RSI 기준, 거래량 배수, 점수 임계값을 바꿔 성능 비교", "추천 기준 개선안"),
        ],
        [1900, 5000, 2460],
    )
    add_callout(
        doc,
        "주의",
        "뉴스 감성 분석은 과거 뉴스 시점과 실제 공개 시간을 기준으로 해야 한다. 미래 정보를 사용하면 백테스트 결과가 왜곡된다.",
        fill=RISK_FILL,
        accent=SUB,
    )

    add_heading(doc, "7. 4단계: 반자동 주문", 1)
    add_para(doc, "반자동 주문은 마지막 단계로 둔다. 분석과 추천이 충분히 검증되기 전에는 주문 API를 연결하지 않는 것이 안전하다.")
    add_bullets(
        doc,
        [
            "주문은 사용자의 명시적 확인 후에만 실행한다.",
            "주문 전 예상 손실, 종목당 투자 비율, 손절/익절 기준을 다시 보여준다.",
            "한국투자 API 또는 키움 API 연동은 샌드박스/모의투자 환경에서 먼저 검증한다.",
            "주문 요청, 성공, 실패, 취소, 재시도는 모두 감사 로그로 남긴다.",
            "자동 주문 전환은 별도 설정으로 잠그고 기본값은 비활성화한다.",
        ]
    )

    add_heading(doc, "8. 추천 일정", 1)
    add_table(
        doc,
        ["기간", "핵심 목표", "주요 산출물"],
        [
            ("1주차", "프로젝트 기반 구축", "API 명세, DB 초안, Flutter UI 골격, Spring/Python 서버 실행"),
            ("2~3주차", "인증·관심종목·자본금", "JWT 로그인, 관심 종목 CRUD, 자본금 설정 화면"),
            ("4~5주차", "RSI·뉴스 분석 MVP", "RSI 계산 API, 뉴스 감성 분석 API, 추천 후보 응답"),
            ("6주차", "알림 MVP", "FCM 토큰 저장, 매수 추천 푸시 알림, 알림 히스토리"),
            ("7~8주차", "점수 시스템", "점수 계산 엔진, 추천 상세 근거, 점수 상태 분류"),
            ("9~10주차", "보유 종목·매도 추천", "손익 계산, 손절/익절 알림, 매도 추천 화면"),
            ("11~12주차", "백테스트 1차", "과거 1년 데이터 기반 전략 검증 리포트"),
            ("이후", "반자동 주문", "모의투자 주문 연동, 승인 화면, 주문 로그"),
        ],
        [1400, 2700, 5260],
    )

    add_heading(doc, "9. 우선 구현할 API와 DB", 1)
    add_table(
        doc,
        ["영역", "API 예시", "DB/저장 대상"],
        [
            ("인증", "POST /auth/signup, POST /auth/login, POST /auth/refresh", "users, refresh_tokens"),
            ("자본금", "GET/PUT /capital", "user_capital"),
            ("관심 종목", "GET/POST/DELETE /watchlist", "watchlist"),
            ("추천", "GET /recommendations, GET /recommendations/{id}", "recommendations, recommendation_reasons"),
            ("보유 종목", "GET/POST/PUT /holdings", "holdings, trade_records"),
            ("알림", "POST /devices/fcm-token, GET /alerts", "device_tokens, alerts"),
            ("AI 연동", "POST /ai/analyze-stock, POST /ai/analyze-news", "analysis_snapshots"),
        ],
        [1400, 3900, 4060],
    )

    add_heading(doc, "10. 완료 기준", 1)
    add_bullets(
        doc,
        [
            "앱: Android 기준으로 로그인부터 추천 상세, 보유 종목, 알림까지 끊김 없이 이동된다.",
            "백엔드: 인증이 필요한 API는 JWT 없이 호출할 수 없고, 사용자별 데이터가 분리된다.",
            "AI 서버: 동일 데이터에 대해 재현 가능한 점수와 추천 사유를 반환한다.",
            "알림: 추천 조건 충족 시 FCM 알림이 발송되고 앱 내 알림 기록에 저장된다.",
            "리스크: 종목당 투자 비율, 손절 기준, 1회 거래 손실 제한이 추천 화면에 반영된다.",
            "운영: 주요 오류는 로그로 추적 가능하고, 외부 API 실패 시 사용자에게 안전한 메시지를 보여준다.",
        ]
    )

    add_heading(doc, "11. 지금 바로 할 다음 작업", 1)
    add_table(
        doc,
        ["우선순위", "작업", "담당 영역"],
        [
            ("P0", "현재 Flutter UI를 실제 API 연동 가능한 화면 구조로 분리", "Frontend"),
            ("P0", "Spring Boot 프로젝트 생성 및 JWT 인증 골격 구현", "Backend"),
            ("P0", "users, user_capital, watchlist 기본 테이블 설계", "Backend/DB"),
            ("P1", "Python AI 서버 FastAPI 또는 Flask 골격 생성", "AI Server"),
            ("P1", "삼성전자 샘플 데이터로 RSI 계산 API 구현", "AI Server"),
            ("P1", "추천 응답 JSON 계약 정의 후 앱에 Mock 연동", "All"),
            ("P2", "뉴스 수집 소스 선정 및 감성 분석 프롬프트/스키마 설계", "AI Server"),
            ("P2", "FCM 프로젝트 설정 및 테스트 푸시 검증", "Backend/Frontend"),
        ],
        [1300, 5600, 2460],
    )

    doc.save(DOCX_PATH)


if __name__ == "__main__":
    build_document()
    print(DOCX_PATH)
