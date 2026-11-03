"""Reviewed KRX XForms HTML tables contained in OpenDART original ZIPs."""
from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlsplit

from .models import ResearchError
from .history import day


@dataclass
class Node:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)

    def walk(self, tag):
        for child in self.children:
            if isinstance(child, Node):
                if child.tag == tag:
                    yield child
                yield from child.walk(tag)

    def text(self):
        if self.tag in {"script", "style", "noscript"}:
            return ""
        return " ".join(" ".join(v.text() if isinstance(v, Node) else v for v in self.children).split())


class XForms(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]
        self.count = 0

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if self.count > 50000 or len(self.stack) > 80 or len(dict(attrs)) != len(attrs):
            raise ResearchError("DISTRIBUTION_HTML_LIMIT")
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if len(self.stack) <= 1 or self.stack[-1].tag != tag:
            raise ResearchError("DISTRIBUTION_HTML_STRUCTURE_INVALID")
        self.stack.pop()

    def handle_data(self, value):
        self.stack[-1].children.append(value)


def parse_html(raw):
    if len(raw) > 8 * 1024 * 1024:
        raise ResearchError("DISTRIBUTION_HTML_LIMIT")
    value = raw.decode("utf-8-sig")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", value, re.I):
        raise ResearchError("DISTRIBUTION_DECLARATION_FORBIDDEN")
    parser = XForms()
    parser.feed(value)
    parser.close()
    if len(parser.stack) != 1 or len(list(parser.root.walk("html"))) != 1:
        raise ResearchError("DISTRIBUTION_HTML_STRUCTURE_INVALID")
    return parser.root


def main_table(root):
    tables = [v for v in root.walk("table") if v.attrs.get("id") == "XFormD1_Form0_Table0"]
    if len(tables) != 1:
        raise ResearchError("DISTRIBUTION_MAIN_TABLE_AMBIGUOUS")
    if list(tables[0].walk("table")):
        raise ResearchError("DISTRIBUTION_NESTED_TABLE_UNSUPPORTED")
    return tables[0]


def related_links(root):
    result = []
    for tr in main_table(root).walk("tr"):
        cells = [v for v in tr.children if isinstance(v, Node) and v.tag == "td"]
        if not cells or "관련공시" not in re.sub(r"\s", "", cells[0].text()):
            continue
        for link in tr.walk("a"):
            parsed = urlsplit(link.attrs.get("href", ""))
            query = parse_qs(parsed.query, keep_blank_values=True)
            if (parsed.scheme not in {"http", "https"} or parsed.netloc != "kind.krx.co.kr" or parsed.path != "/common/disclsviewer.do"
                    or parsed.fragment or query.get("method") != ["search"] or any(len(v) != 1 for v in query.values())
                    or set(query) - {"method", "acptno", "rcpno", "orgid", "tran", "langTpCd"}
                    or not re.fullmatch(r"[0-9]{14}", query.get("rcpno", [""])[0])):
                raise ResearchError("DISTRIBUTION_RELATED_LINK_INVALID")
            label = link.text()
            compact = re.sub(r"\s", "", label)
            role = "TREASURY_ACQUISITION_RESULT" if compact.endswith("자기주식취득결과보고서") else "TREASURY_ACQUISITION_DECISION" if compact.endswith("자기주식취득결정") else "UNSUPPORTED"
            if role != "UNSUPPORTED":
                if not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}자기주식취득(?:결과보고서|결정)", compact):
                    raise ResearchError("DISTRIBUTION_RELATED_DATE_INVALID")
                day(compact[:10])
            result.append({"receiptNumber": query["rcpno"][0], "role": role, "label": label,
                           "sourceHref": link.attrs["href"]})
    if len({v["receiptNumber"] for v in result}) != len(result):
        raise ResearchError("DISTRIBUTION_RELATED_LINK_AMBIGUOUS")
    return result


def only(values):
    values = list(values)
    if len(values) != 1:
        raise ResearchError("DISTRIBUTION_FIELD_AMBIGUOUS")
    return values[0]


def compact(value):
    return re.sub(r"\s", "", value)


def decimal(value):
    if value == "-":
        return None
    if not re.fullmatch(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]{1,8})?", value):
        raise ResearchError("DISTRIBUTION_NUMBER_INVALID")
    result = value.replace(",", "")
    if len(result.split(".")[0]) > 18:
        raise ResearchError("DISTRIBUTION_NUMBER_LIMIT")
    return result


def extract_distribution(raw, selected, company_names):
    root = parse_html(raw)
    title = only(root.walk("title")).text()
    parts = title.split("/")
    expected = compact(selected["reportName"])
    if (len(parts) != 3 or compact(parts[0]) not in {compact(v) for v in company_names}
            or compact(parts[1]) != expected or parts[2] != "(" + selected["receiptDate"].replace("-", ".") + ")" + parts[1]
            or selected["correctionIndicated"] or selected["withdrawalIndicated"]):
        raise ResearchError("DISTRIBUTION_ISSUER_TITLE_UNSUPPORTED")
    table = main_table(root)
    rows = [[c for c in tr.children if isinstance(c, Node) and c.tag == "td"] for tr in table.walk("tr")]
    if len(rows) > 1000:
        raise ResearchError("DISTRIBUTION_ROW_LIMIT")
    def locate(label):
        return only(i for i, cells in enumerate(rows) if cells and compact(cells[0].text()) == compact(label))
    def evidence(index, cell):
        return {"tableId": table.attrs["id"], "rowIndex": index, "cellIndex": cell, "sourceText": rows[index][cell].text()}
    def scalar(label):
        index = locate(label)
        if len(rows[index]) != 2:
            raise ResearchError("DISTRIBUTION_SCALAR_LAYOUT_INVALID")
        return rows[index][1].text(), evidence(index, 1)
    def numeric(label, role, unit):
        value, proof = scalar(label)
        return {"role": role, "shareClass": "ALL", "unit": unit, "value": decimal(value), "evidence": proof}
    def pair(label, role, unit, common_label, other_label):
        index = locate(label)
        if (index + 1 >= len(rows) or len(rows[index]) != 3 or len(rows[index+1]) != 2
                or rows[index][0].attrs.get("rowspan") != "2" or compact(rows[index][1].text()) != compact(common_label)
                or compact(rows[index+1][0].text()) != compact(other_label)):
            raise ResearchError("DISTRIBUTION_SHARE_CLASS_LAYOUT_INVALID")
        return [{"role": role, "shareClass": cls, "unit": unit, "value": decimal(rows[i][c].text()), "evidence": evidence(i, c)}
                for cls, i, c in [("COMMON", index, 2), ("OTHER", index+1, 1)]]
    def date(label, role):
        value, proof = scalar(label)
        if value != "-": day(value)
        return {"role": role, "value": None if value == "-" else value, "precision": "DATE", "evidence": proof}
    if expected == "현금ㆍ현물배당결정":
        if scalar("2. 배당종류")[0] != "현금배당":
            raise ResearchError("DISTRIBUTION_DIVIDEND_TYPE_UNSUPPORTED")
        kind, doc_type = "CASH_DIVIDEND_PLAN", "KRX_CASH_DIVIDEND_DECISION"
        numbers = pair("3. 1주당 배당금(원)", "DIVIDEND_PER_SHARE", "KRW_PER_SHARE", "보통주식", "종류주식")
        numbers += pair("4. 시가배당율(%)", "DECLARED_DIVIDEND_YIELD", "PERCENT", "보통주식", "종류주식")
        numbers += [numeric("5. 배당금총액(원)", "TOTAL_DIVIDEND_AMOUNT", "KRW")]
        dates = [date(label, role) for label, role in [("6. 배당기준일", "RECORD_DATE"), ("7. 배당금지급 예정일자", "PAYMENT_PLANNED_DATE"),
                 ("9. 주주총회 예정일자", "MEETING_PLANNED_DATE"), ("10. 이사회결의일(결정일)", "DECISION_DATE")]]
        unconfirmed = ["EX_DATE", "ACTUAL_PAYMENT_DATE"]
    elif expected == "주식소각결정":
        kind, doc_type = "SHARE_CANCELLATION_PLAN", "KRX_SHARE_CANCELLATION_DECISION"
        numbers = pair("1. 소각할 주식의 종류와 수", "PLANNED_CANCELLATION", "SHARES", "보통주식 (주)", "종류주식 (주)")
        numbers += pair("2. 발행주식 총수", "REPORTED_ISSUED_SHARES", "SHARES", "보통주식 (주)", "종류주식 (주)")
        numbers += [numeric("3. 1주당 가액(원)", "FACE_VALUE_PER_SHARE", "KRW_PER_SHARE"), numeric("4. 소각예정금액(원)", "PLANNED_CANCELLATION_AMOUNT", "KRW")]
        index = locate("5. 소각을 위한 자기주식 취득 예정기간")
        if (rows[index][0].attrs.get("rowspan") != "2" or len(rows[index]) != 3 or len(rows[index+1]) != 2
                or rows[index][1].text() != "시작일" or rows[index+1][0].text() != "종료일"):
            raise ResearchError("DISTRIBUTION_PERIOD_LAYOUT_INVALID")
        dates = []
        for role, i, cell in [("ACQUISITION_PLANNED_START", index, 2), ("ACQUISITION_PLANNED_END", index+1, 1)]:
            value = rows[i][cell].text()
            if value != "-": day(value)
            dates.append({"role": role, "value": None if value == "-" else value, "precision": "DATE", "evidence": evidence(i, cell)})
        dates += [date("7. 소각 예정일", "CANCELLATION_PLANNED_DATE"), date("9. 이사회결의일(결정일)", "DECISION_DATE")]
        unconfirmed = ["ACTUAL_CANCELLATION_DATE"]
        for cls in ["COMMON", "OTHER"]:
            values = {v["role"]: v["value"] for v in numbers if v["shareClass"] == cls}
            if any(v is None or "." in v for v in values.values()) or int(values["PLANNED_CANCELLATION"]) > int(values["REPORTED_ISSUED_SHARES"]):
                raise ResearchError("DISTRIBUTION_SHARE_COUNT_INVALID")
    else:
        raise ResearchError("DISTRIBUTION_FORM_UNSUPPORTED")
    by_role = {v["role"]: v["value"] for v in dates}
    decision = by_role["DECISION_DATE"]
    if decision is None:
        raise ResearchError("DISTRIBUTION_DECISION_DATE_MISSING")
    for role in ["PAYMENT_PLANNED_DATE", "MEETING_PLANNED_DATE", "CANCELLATION_PLANNED_DATE"]:
        value = by_role.get(role)
        if value is not None and value < decision:
            raise ResearchError("DISTRIBUTION_DATE_ORDER_INVALID")
    start, end = by_role.get("ACQUISITION_PLANNED_START"), by_role.get("ACQUISITION_PLANNED_END")
    if start is not None and end is not None and start > end:
        raise ResearchError("DISTRIBUTION_DATE_ORDER_INVALID")
    return {"documentType": doc_type, "formulaVersion": "REVIEWED_KRX_XFORMS_V1", "kind": kind, "dates": dates, "numbers": numbers,
            "instrument": {"scope": "ISSUER_SHARE_CLASSES", "otherShareClassStockCode": None},
            "correction": {"present": False, "chainStatus": "NOT_ESTABLISHED", "directParentReceiptNumber": None},
            "relatedDocuments": related_links(root), "unconfirmedDateRoles": unconfirmed,
            "normalization": {"format": "HTML_XFORMS", "decodedAs": "UTF-8", "rawCharsetDeclarationTrusted": False}}
