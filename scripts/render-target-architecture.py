"""Render the editable target diagram and its PNG from one layout.

Run from any directory: python scripts/render-target-architecture.py
Requires Pillow and a Korean-capable font (Malgun Gothic on Windows).
Only writes docs/images/target-system-architecture.{svg,png}; no network calls.
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 2400, 1870
COLORS = {
    "bg": "#101720", "panel": "#17222f", "card": "#1e2d3e",
    "border": "#3e536b", "text": "#f1f6fc", "muted": "#b8c9da",
    "blue": "#62bdff", "green": "#42ddb0", "amber": "#ffc168",
    "purple": "#c4a3ff", "learning": "#242238",
}


def locate_font(override: str | None, bold: bool = False) -> Path:
    if override:
        path = Path(override)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [
        windows_fonts / ("malgunbd.ttf" if bold else "malgun.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold
             else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError("Korean font required; specify --font and --font-bold.")


class Diagram:
    def __init__(self, regular: Path, bold: Path):
        self.regular, self.bold = regular, bold
        self.image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg"])
        self.draw = ImageDraw.Draw(self.image)
        self.fonts: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}
        self.svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
            '<title id="title">SagoPalgo 실시간 AI 자동매매 목표 아키텍처</title>',
            '<desc id="desc">현재 기반의 확장과 신규 개발을 구분합니다. 시세와 사건 수집, '
            '시장 탐색, 모델 판단, 자금 검증, KB 주문과 체결 환류, 별도 과거 학습 경로를 보여줍니다. '
            '현재 배포 구조가 아닌 목표 설계입니다.</desc>',
            f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{COLORS["bg"]}"/>',
        ]

    def font(self, size: int, bold: bool = False):
        key = size, bold
        if key not in self.fonts:
            self.fonts[key] = ImageFont.truetype(str(self.bold if bold else self.regular), size)
        return self.fonts[key]

    def text(self, x, y, value, size=25, color="text", bold=False, max_width=None):
        font = self.font(size, bold)
        actual_width = self.draw.textlength(value, font=font)
        if max_width is not None and actual_width > max_width:
            raise ValueError(f"Text overflow ({actual_width:.1f}>{max_width}): {value}")
        if x < 0 or x + actual_width > WIDTH or y < 0 or y + size > HEIGHT:
            raise ValueError(f"Text outside canvas: {value}")
        fill = COLORS.get(color, color)
        self.draw.text((x, y), value, fill=fill, font=font, anchor="lt")
        # Font ascent keeps the raster/vector top alignment consistent.
        bbox = self.draw.textbbox((0, 0), value, font=font, anchor="ls")
        baseline = y - bbox[1]
        self.svg.append(
            f'<text x="{x}" y="{baseline}" fill="{fill}" '
            f'font-family="Malgun Gothic, Noto Sans CJK KR, sans-serif" font-size="{size}" '
            f'font-weight="{700 if bold else 400}">{escape(value)}</text>'
        )

    def line(self, points, color="blue", width=3, dashed=False, arrow=False):
        fill = COLORS.get(color, color)
        if dashed:
            for (x1, y1), (x2, y2) in zip(points, points[1:]):
                length = math.hypot(x2-x1, y2-y1)
                if not length:
                    continue
                for start in range(0, math.ceil(length), 17):
                    end = min(start+10, length)
                    self.draw.line((x1+(x2-x1)*start/length, y1+(y2-y1)*start/length,
                                    x1+(x2-x1)*end/length, y1+(y2-y1)*end/length),
                                   fill=fill, width=width)
        else:
            self.draw.line(points, fill=fill, width=width, joint="curve")
        coords = " ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="10 7"' if dashed else ""
        self.svg.append(f'<polyline points="{coords}" fill="none" stroke="{fill}" '
                        f'stroke-width="{width}" stroke-linejoin="round"{dash}/>')
        if arrow:
            (x1, y1), (x2, y2) = points[-2:]
            angle = math.atan2(y2-y1, x2-x1)
            tip = (x2, y2)
            base_x, base_y = x2-15*math.cos(angle), y2-15*math.sin(angle)
            tri = [tip, (base_x+7*math.sin(angle), base_y-7*math.cos(angle)),
                   (base_x-7*math.sin(angle), base_y+7*math.cos(angle))]
            self.draw.polygon(tri, fill=fill)
            self.svg.append('<polygon points="' + " ".join(f"{x:.2f},{y:.2f}" for x,y in tri)
                            + f'" fill="{fill}"/>')

    def rect(self, x, y, w, h, fill="card", stroke="border", dashed=False, radius=16):
        fill, stroke = COLORS.get(fill, fill), COLORS.get(stroke, stroke)
        if dashed:
            self.draw.rectangle((x,y,x+w,y+h), fill=fill)
            self.line([(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)], stroke, 2, True)
            self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>')
            self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                            f'fill="none" stroke="{stroke}" stroke-width="2" stroke-dasharray="10 7"/>')
        else:
            self.draw.rounded_rectangle((x,y,x+w,y+h), radius, fill=fill, outline=stroke, width=2)
            self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
                            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>')

    def node(self, x, y, w, h, title, lines, new=False, accent=None):
        stroke = accent or ("amber" if new else "blue")
        self.rect(x,y,w,h,stroke=stroke,dashed=new)
        self.text(x+22,y+20,title,27,stroke,True,w-44)
        for i, value in enumerate(lines):
            self.text(x+22,y+64+i*36,value,24,"muted",max_width=w-44)
        if 64+len(lines)*36 > h+10:
            raise ValueError(f"Node vertical overflow: {title}")

    def save(self, output: Path):
        output.mkdir(parents=True, exist_ok=True)
        self.svg.append("</svg>")
        (output/"target-system-architecture.svg").write_text("\n".join(self.svg)+"\n", encoding="utf-8")
        self.image.save(output/"target-system-architecture.png", optimize=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", help="Regular Korean TTF/TTC path")
    parser.add_argument("--font-bold", help="Bold Korean TTF/TTC path")
    args = parser.parse_args()
    d = Diagram(locate_font(args.font), locate_font(args.font_bold or args.font, True))
    d.text(55,43,"SagoPalgo · 실시간 AI 자동매매 목표 구조",48,bold=True)
    d.text(55,111,"목표 설계 · 2026-11-02 · 신규 경로는 미구현 / 현재 배포 구조와 별도 관리",27,"muted")
    d.rect(1390,42,390,55,stroke="blue")
    d.text(1410,55,"실선: 기존 기반을 확장",25,"blue")
    d.rect(1810,42,535,55,stroke="amber",dashed=True)
    d.text(1830,55,"점선: 신규 개발 · 완료 표시 아님",25,"amber")

    d.rect(50,200,370,1230,fill="panel")
    d.rect(450,200,1460,1230,fill="panel")
    d.rect(1940,200,410,1230,fill="panel")
    d.text(78,226,"Windows PC",32,"green",True)
    d.text(480,226,"Ubuntu 상시 서버 · Docker 기반 확장",32,"blue",True)
    d.text(1970,226,"외부 Provider",32,"amber",True)

    d.node(80,290,310,270,"Flutter Windows",[
        "차트 · 계좌 · 관심종목", "후보 · AI 판단 근거", "일·주·월·연 수익", "서버 상태를 실시간 표시"],accent="green")
    d.node(80,670,310,200,"운용 설정·제어",[
        "자금 · 전략 · 한도", "활성화 · 중지 · 재개", "미확정 주문 확인"],new=True)
    d.node(80,1040,310,200,"운영 진단·알림",[
        "데이터 지연 · 연결", "체결 · 위험 · 손익", "판단과 주문 감사 이력"],accent="green")
    d.text(80,1300,"앱 종료 중에도",25,"green",True)
    d.text(80,1342,"서버는 운용 정책을 유지",23,"muted",max_width=310)

    d.node(490,290,1380,100,"Nginx + Spring API · 요청 / 실시간 전달 / 운용 명령",[
        "기존 사설망·IP 제한 유지 + 제어 인증 보강 · 앱 요청과 이벤트 전달의 진입점"])

    d.node(490,480,420,150,"01 수집·정규화",["체결·호가 / 수급 / 뉴스·공시", "시각 · 거래소 · 출처 · 품질"])
    d.node(970,480,420,150,"02 이벤트·최신 상태",["버퍼 · 체크포인트 · 중복 제거", "원본 기록 A · 장중 봉 · 구독"],new=True)
    d.node(1450,480,420,150,"03 시장 전체 탐색",["경량 필터 → 제한 후보군", "보유·관심종목 관리 우선"],new=True)
    d.node(490,770,420,185,"04 특징·추론·전략",[
        "승인 모델 B · 실시간 재판단", "매수/매도/관망 · 근거·유효기한", "목표 비중 · 예상 수익·위험"],new=True)
    d.node(970,770,420,185,"05 자금 배분·위험",[
        "실잔고 · 보유 · 미체결 예약", "종목/손실/유동성 한도 검증", "계좌별 원자적 현금·수량 예약"],new=True)
    d.node(1450,770,420,185,"06 주문 실행·복구",[
        "기존 주문 코어 · KB로만 전송", "온주 / 소수점 별도 계약", "중복 방지 · 불명확 응답 대조"])
    d.node(1450,1080,420,185,"07 계좌·체결 동기화",[
        "접수 ≠ 체결 · 부분 체결 반영", "수동 거래 · 미체결 · 잔고 대조", "재시작 후 실제 계좌로 복구"])
    d.node(970,1080,420,185,"08 원장·자산 기록",[
        "체결 · 비용 · 입출금 · 배당", "보유·예약 갱신 · 일별 평가", "MySQL 기반 확장 · 감사 A"])
    d.node(490,1080,420,185,"09 성과·운영 집계",[
        "일·주·월·연 수익 · 자산 곡선", "전략별 성과 · 노출 · 최대 낙폭", "현재 평가와 저장 시점을 구분"],new=True)

    d.node(1980,300,330,150,"시세·수급",["KIS / KB / Toss", "지원 확인된 읽기 전용"])
    d.node(1980,490,330,150,"뉴스·공시",["Naver / OpenDART", "제공 속도·한도 내 수집"])
    d.node(1980,770,330,420,"KB 실계좌·주문",[
        "계좌 · 잔고 · 미체결", "주문 → 접수 → 체결", "정정 · 취소 · 체결 조회", "", "소수점은 체결 주기와", "배분 계약을 별도 검증", "", "관심목록·스트리밍은", "지원 확정 후 연결"])

    # Data ingress stays outside the API panel and operational nodes.
    d.line([(1980,375),(1925,375),(1925,430),(700,430),(700,480)],"green",arrow=True)
    d.line([(1980,565),(1925,565),(1925,430)],"green")
    d.text(1020,402,"공급자별 시각·품질을 보존",22,"green")
    d.line([(910,555),(970,555)],arrow=True)
    d.line([(1390,555),(1450,555)],arrow=True)
    d.line([(1660,630),(1660,700),(700,700),(700,770)],arrow=True)
    d.line([(1180,630),(1180,700)],arrow=True)
    d.text(980,664,"후보 + 최신 데이터 → 재평가",23,"blue")
    d.line([(910,860),(970,860)],arrow=True)
    d.line([(1390,860),(1450,860)],arrow=True)
    d.line([(1870,850),(1980,850)],"amber",arrow=True)
    d.text(1890,815,"주문",22,"amber")
    d.line([(1980,1145),(1870,1145)],"amber",arrow=True)
    d.text(1890,1109,"대조",22,"amber")
    d.line([(1660,955),(1660,1080)],arrow=True)
    d.text(1677,1005,"체결 확인",22,"blue")
    d.line([(1450,1170),(1390,1170)],arrow=True)
    d.line([(970,1170),(910,1170)],arrow=True)
    d.line([(1450,1115),(1420,1115),(1420,1000),(1180,1000),(1180,955)],"green",arrow=True)
    d.text(1050,1021,"잔고·예약·체결 환류",22,"green")
    d.line([(490,1170),(470,1170),(470,410),(520,410),(520,390)],"green",arrow=True)
    d.line([(390,335),(490,335)],"green",arrow=True)
    d.line([(490,365),(435,365),(435,510),(390,510)],"green",arrow=True)
    d.line([(390,740),(440,740),(440,320),(490,320)],"amber",dashed=True,arrow=True)
    d.text(520,1314,"논리 모듈 구분 · 상자마다 컨테이너를 추가하는 설계가 아님",25,"muted")
    d.text(520,1360,"주문 전 데이터·계좌·위험 검증 / 장애 시 진입 중지·대조 / 기본 자동매매 OFF",24,"muted")

    d.rect(50,1470,2300,290,fill="learning",stroke="purple")
    d.text(80,1495,"과거 데이터·학습 경로 · 장중 추론/주문과 별도 실행",31,"purple",True)
    d.node(80,1555,490,150,"A 원본 기록 + 과거 자료",["시세·호가·수급·사건·계좌 이력", "데이터 버전 · 공개 시점 · 기업행사"],new=True,accent="purple")
    d.node(650,1555,490,150,"정제·학습 데이터셋",["미래 정보·생존 편향·결측 검사", "학습/추론에 같은 특징 정의"],new=True,accent="purple")
    d.node(1220,1555,490,150,"학습·시간 순서 검증",["독립 평가 · 비용·부분 체결 재현", "shadow / 실시간 모의 평가"],new=True,accent="purple")
    d.node(1790,1555,530,150,"B 모델 버전·배포 승인",["검증 통과 버전 → 04 추론에 적용", "특징·전략 버전 / 이전 모델 복구"],new=True,accent="purple")
    for x in (570,1140,1710):
        d.line([(x,1630),(x+80,1630)],"purple",arrow=True)
    d.text(80,1723,"A = 운영 기록을 학습에 활용 · B = 승인 버전을 운영 추론에 공급 · 학습 완료만으로 실주문을 활성화하지 않음",22,"purple")
    d.text(55,1800,"국내 온주·국내/해외 소수점은 상품별 체결 계약에 맞춰 분리 · API 지원과 즉시 체결 가능 여부는 별도 확인",24,"muted")
    d.save(ROOT / "docs" / "images")
    print(f"Rendered {WIDTH}x{HEIGHT}: docs/images/target-system-architecture.svg and .png")


if __name__ == "__main__":
    main()
