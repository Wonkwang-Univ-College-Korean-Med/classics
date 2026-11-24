# -*- coding: utf-8 -*-
"""『중국 국의대사 경험방 R&D 인사이트』(한국한의학연구원, 2026) PDF 텍스트 층 → 구조화 데이터.

PDF는 Chrome(Skia)으로 HTML을 인쇄한 것이라 글자가 그대로 들어 있다. 글꼴 크기·색·좌표로
장절·카드·표를 가려 처방 66종을 구조화한다. extract_lines.py 가 만든 lines.json 을 읽는다.
"""
import html
import json
import os
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))

ACCENTS = {"1f7a6c": 1, "b0533c": 2, "a47719": 3, "5b4a9e": 4, "2b79a3": 5}
EYEBROWS = {"IDENTITY": "identity", "COMPOSITION": "composition", "MASTER'STHOUGHT": "master",
            "R&D인사이트": "rd", "RESEARCHEVIDENCE": "evidence", "DATAEVIDENCE": "data", "CHINAPRODUCTS": "china"}
HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
HANGUL = re.compile(r"[가-힣]")


class Ln:
    __slots__ = ("p", "x", "y", "x2", "y2", "s", "c", "t")

    def __init__(self, r):
        self.p, self.x, self.y, self.x2, self.y2, self.s, self.c, self.t = r
        self.t = self.t.replace("\u00a0", " ").rstrip()

    @property
    def Y(self):
        return self.p * 1000 + self.y

    def __repr__(self):
        return f"<{self.p}:{self.x:.0f},{self.y:.0f} {self.s} {self.c} {self.t[:30]}>"


def load():
    return [Ln(r) for r in json.load(open(os.path.join(HERE, "lines.json"), encoding="utf-8"))]


def is_chrome(l):
    """머리말·쪽 번호·옆 탭 등 장식 줄"""
    if l.y < 52 and l.s <= 7.6:
        return True
    if l.y > 795 and l.c == "6b7388" and l.t.strip().isdigit():
        return True
    if l.c == "ffffff" and l.s == 9.0 and (l.x > 575 or (60 < l.x < 70 and l.t.strip().isdigit())):
        return True
    return False


def glue(a, b):
    if not a or not b:
        return ""
    x, y = a[-1], b[0]
    if HAN.match(x) or HAN.match(y) or re.match(r"^\[\d", b):
        return ""
    if x in "(/–-“‘「《[" or y in ")]」》’”,.:;·":
        return ""
    last = re.split(r"\s", a)[-1]
    if x.isascii() and y.isascii() and (("/" in last) or last[-1:].isdigit() and (y.isdigit() or y == "(")):
        return ""
    return " "


def esc(s):
    return html.escape(s, quote=False)


def rich(s):
    """본문 글 → HTML(문장 앞 '라벨:' 강조)"""
    s = esc(s)
    s = re.sub(r"^((?:검증 설계|의미|근거|증상|현대적 매핑|R&amp;D 타깃|데이터 분석|통계적 시사점))(?=\S)", r"<b>\1</b> ", s)
    m = re.match(r"^([^:：<]{1,40}?)[:：]\s", s)
    if m and not s.startswith("<b>") and not re.search(r"https?$", m.group(1)):
        s = f"<b>{m.group(1)}</b>:" + s[len(m.group(1)) + 1:]
    return s


# ───────────── 줄 묶기(행 → 문단·표) ─────────────
def rows_of(lines, tol=2.6):
    rows = []
    for l in sorted(lines, key=lambda l: (l.p, l.y, l.x)):
        if rows and rows[-1][0].p == l.p and abs(rows[-1][0].y - l.y) <= tol:
            rows[-1].append(l)
        else:
            rows.append([l])
    for r in rows:
        r.sort(key=lambda l: l.x)
    return rows


def is_head_cell(l, accent):
    return (l.c == accent and l.s in (8.4, 8.0, 7.0) and not l.t.startswith("그림")) or (l.c == "6b7388" and l.s in (7.4, 7.6, 7.0)) \
        or (l.c == "ffffff" and l.s in (7.6, 8.4))


def chart_extract(lines):
    """막대그래프(축 눈금 8d96a8·값 1f4e6b) → 가로 막대 HTML"""
    vals = [l for l in lines if l.c in ("8d96a8", "1f4e6b") and l.s <= 7.0]
    if len(vals) < 6:
        return "", lines
    ys = sorted(l.y for l in vals)
    page = vals[0].p
    base_y = max(l.y for l in vals)
    labels = [l for l in lines if l.p == page and l.s == 7.4 and abs(l.y - (base_y + 9.4)) < 8]
    if not labels:
        labels = [l for l in lines if l.p == page and l.s == 7.4 and l.y > base_y]
    bars = []
    for lb in sorted(labels, key=lambda l: l.x):
        cx = (lb.x + lb.x2) / 2
        cand = [v for v in vals if v.s == 6.8 and abs((v.x + v.x2) / 2 - cx) < 12]
        if cand:
            v = min(cand, key=lambda v: abs((v.x + v.x2) / 2 - cx))
            bars.append((lb.t, int(v.t), v.c == "1f4e6b"))
    used = set(id(l) for l in vals) | set(id(l) for l in labels)
    axis = [l for l in lines if l.p == page and l.s in (7.1,) and l.t.strip() == "빈도"]
    used |= set(id(l) for l in axis)
    legend = [l for l in lines if l.p == page and l.s == 7.8 and l.c == "3d4760" and l.y > base_y]
    used |= set(id(l) for l in legend)
    mx = max(b[1] for b in bars) if bars else 1
    h = ['<div class="chart"><p class="cap">사용 빈도 상위 약재(막대: 짙은 색 = 처방 구성 약재)</p>']
    for name, v, own in bars:
        h.append(f'<div class="bar{" own" if own else ""}"><span>{esc(name)}</span><i style="width:{v / mx * 100:.1f}%"></i><b>{v}</b></div>')
    h.append("</div>")
    return "".join(h), [l for l in lines if id(l) not in used]


def flow_html(lines, accent):
    """한 절의 줄들을 HTML로(소제목·문단·글머리표·표·캡션·참고문헌)"""
    chart, lines = chart_extract([l for l in lines if not is_chrome(l)])
    rows = rows_of(lines)
    out = []
    i = 0
    para = None   # [style_key, x, last_line, text, cls]

    def flush():
        nonlocal para
        if para:
            cls, txt = para[4], para[3]
            if cls == "h":
                out.append(f"<h4>{esc(txt)}</h4>")
            elif cls == "cap":
                out.append(f'<p class="cap">{esc(txt)}</p>')
            elif cls == "ref":
                out.append(f'<li class="ref">{linkify(esc(txt))}</li>')
            elif cls == "note":
                out.append(f'<p class="note">{rich(txt)}</p>')
            elif cls == "box":
                out.append(f'<p class="box">{rich(txt)}</p>')
            elif cls == "li":
                out.append(f'<p class="li">{rich(txt)}</p>')
            elif cls == "sub":
                out.append(f'<p class="sub">{rich(txt)}</p>')
            elif cls == "quote":
                out.append(f'<p class="quote">{rich(txt)}</p>')
            elif cls == "big":
                out.append(f'<p class="big">{rich(txt)}</p>')
            elif cls == "label":
                out.append(f'<p class="lbl">{esc(txt)}</p>')
            elif para[5] == 1 and len(txt) <= 24 and not re.search(r"[.,:;]", txt) and para[2].s >= 9.5:
                out.append(f'<p class="lbl2">{esc(txt)}</p>')
            else:
                out.append(f"<p>{rich(txt)}</p>")
        para = None

    def classify(l):
        if l.s == 10.2 and l.c in ACCENTS:
            return "h"
        if l.s == 10.2 and l.c == "3d4760":
            return "hcont"
        if l.t.startswith("그림") and l.c in ACCENTS:
            return "cap"
        if re.match(r"^\[\d+\]", l.t) and l.s <= 7.4:
            return "ref"
        if l.s <= 7.4 and l.c in ("4e566a", "6b7388", "16213a") and refmode[0]:
            return "refcont"
        if l.t.startswith("※") or (l.s == 8.0 and l.c == "6b7388"):
            return "note"
        if l.c == "ffffff" and l.s >= 9:
            return "box"
        if l.s == 7.2 and l.c == "9fb6e8":
            return "boxlabel"
        if l.s == 7.2 and l.c in ACCENTS:
            return "label"
        if l.t.lstrip().startswith(("•", "·", "- ", "→")) and len(l.t) > 2:
            return "li"
        if l.s == 9.6 and l.t.startswith(("“", "\"")):
            return "quote"
        if l.s == 10.0 and l.c == "3d4760":
            return "big"
        if l.s in (9.1,) and l.c == "3d4760":
            return "sub"
        if l.s == 7.0 and l.c in ACCENTS:
            return "label"
        return "p"

    refmode = [False]
    while i < len(rows):
        r = rows[i]
        # 표: 머리줄(2칸 이상) 뒤 행들
        if len(r) >= 2 and all(is_head_cell(c, accent) for c in r) and not any(c.t.startswith("그림") for c in r):
            flush()
            cols = [c.x for c in r]
            head = [c.t for c in r]
            body = []
            j = i + 1
            last_y = r[0].Y
            cur = None
            while j < len(rows):
                rr = rows[j]
                if rr[0].x < cols[0] - 8 or rr[0].s in (10.2, 13.0, 6.9) or (len(rr) == 1 and rr[0].s >= 9.6 and rr[0].x < cols[0] - 2):
                    break
                page_turn = rr[0].p != (last_y // 1000)
                if page_turn:
                    # 다음 쪽 맨 위에서 같은 칸 위치로 이어지는 표만 잇는다
                    if rr[0].y > 130 or rr[0].x < cols[0] - 3:
                        break
                elif rr[0].Y - last_y > 40:
                    break
                cells = [[] for _ in cols]
                for c in rr:
                    k = max([n for n, cx in enumerate(cols) if cx <= c.x + 6] or [0])
                    cells[k].append(c)
                first = cells[0][0].t if cells[0] else ""
                gap = 0 if page_turn and not cells[0] else (100 if page_turn else rr[0].Y - last_y)
                stat = head[0].startswith("Total Papers")
                new_row = cur is None or (not stat and (gap > 19 or first.startswith("[")))
                if new_row:
                    cur = [list(x) for x in cells]
                    body.append(cur)
                else:
                    for k, x in enumerate(cells):
                        cur[k].extend(x)
                last_y = rr[0].Y
                j += 1
            h = ['<div class="tbl"><table><thead><tr>' + "".join(f"<th>{esc(x)}</th>" for x in head) + "</tr></thead><tbody>"]
            for row in body:
                tds = []
                for k, parts in enumerate(row):
                    if parts and (all(p.s == 7.8 for p in parts) or "키워드" in head[k]):
                        tds.append("<td>" + " ".join(f'<span class="kw">{esc(p.t)}</span>' for p in parts) + "</td>")
                        continue
                    if any(p.t.startswith(("·", "•", "→")) for p in parts[1:]) or (parts and parts[0].t.startswith(("·", "•"))):
                        items, buf = [], ""
                        for p in parts:
                            if p.t.startswith(("·", "•", "→")):
                                if buf:
                                    items.append(buf)
                                buf = p.t.lstrip("·• ") if not p.t.startswith("→") else p.t
                            else:
                                buf += (glue(buf, p.t) if buf else "") + p.t
                        if buf:
                            items.append(buf)
                        tds.append("<td>" + "<br>".join(("" if x.startswith("→") else "· ") + rich(x) for x in items) + "</td>")
                        continue
                    joined = ""
                    for p in parts:
                        joined += (glue(joined, p.t) if joined else "") + p.t
                    cls = ' class="k"' if parts and parts[0].c in ACCENTS and k == 0 else ""
                    tds.append(f"<td{cls}>{rich(joined)}</td>")
                h.append("<tr>" + "".join(tds) + "</tr>")
            h.append("</tbody></table></div>")
            out.append("".join(h))
            i = j
            continue
        # 여러 칸 행(표가 아님): 칸을 이어 한 줄로
        if len(r) >= 2:
            flush()
            cls0 = classify(r[0])
            if cls0 == "h":
                out.append(f"<h4>{esc(' '.join(c.t for c in r))}</h4>")
            else:
                parts = []
                for c in r:
                    if c.c == "ffffff" or (c.s == 7.0 and c.c in ("5a6275", "2c3e70")):
                        parts.append(f'<span class="chip">{esc(c.t)}</span>')
                    elif c.c in ACCENTS and c.s <= 8.4:
                        parts.append(f"<b>{esc(c.t)}</b>")
                    else:
                        parts.append(rich(c.t))
                txt = " ".join(parts)
                # 다음 줄이 같은 색으로 이어지면(카드의 '근거' 줄 넘김) 붙인다
                while i + 1 < len(rows) and len(rows[i + 1]) == 1:
                    nl = rows[i + 1][0]
                    if 0 < nl.Y - r[-1].Y <= 16 and nl.c == r[-1].c and nl.x >= r[0].x - 2 and nl.s <= 8.6:
                        txt += glue(r[-1].t, nl.t) + rich(nl.t)
                        r = r[:-1] + [nl]
                        i += 1
                    else:
                        break
                out.append('<p class="row">' + txt + "</p>")
            i += 1
            continue
        l = r[0]
        cls = classify(l)
        if cls == "ref":
            refmode[0] = True
        if cls == "refcont":
            cls = "ref"
            if para and para[4] == "ref":
                para[3] += glue(para[3], l.t) + l.t
                para[2] = l
                para[5] += 1
                i += 1
                continue
        if cls == "hcont" and para and para[4] == "h":
            para[3] += " " + l.t
            i += 1
            continue
        if cls == "boxlabel":
            flush()
            out.append(f'<p class="boxlbl">{esc(l.t)}</p>')
            i += 1
            continue
        if para:
            gap = l.Y - para[2].Y
            same = (para[4] == cls or (para[4] in ("p", "li", "sub", "box", "quote", "note") and cls == "p")) \
                and abs(l.x - para[1]) < 3.5 + (12 if para[4] == "li" else 0) and 0 < gap <= max(l.s, para[2].s) * 2.05 \
                and cls not in ("h", "cap") and not (cls == "li" and para[4] == "li" and l.t.lstrip().startswith(("•", "·")))
            if cls == "ref" and para[4] == "ref":
                same = False
            if same:
                para[3] += glue(para[3], l.t) + l.t
                para[2] = l
                para[5] += 1
                i += 1
                continue
        flush()
        para = [None, l.x, l, l.t, cls if cls != "hcont" else "p", 1]
        i += 1
    flush()
    h = "".join(out)
    h = re.sub(r"((?:<li class=\"ref\">.*?</li>)+)", r'<ol class="refs">\1</ol>', h)
    return h + chart


def linkify(s):
    return re.sub(r"(https?://[^\s<>\]）)]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', s)


# ───────────── 카드(R&D 인사이트) ─────────────
def cards_html(lines, accent):
    lines = [l for l in lines if not is_chrome(l)]
    rd_heads = [l for l in lines if l.s == 6.4 and "M O D E R N" in l.t]
    lg_heads = [l for l in lines if l.s == 6.4 and "T C M" in l.t.replace("TC M", "T C M") or (l.s == 6.4 and "대사의 논리" in l.t)]
    intro = [l for l in lines if l.s in (13.0, 6.9)]
    rd, lg = [], []

    def group(heads, col_pred):
        heads = sorted(heads, key=lambda l: l.Y)
        res = []
        for k, hd in enumerate(heads):
            nxt = heads[k + 1].Y if k + 1 < len(heads) else 10 ** 9
            # 같은 쪽 안에서 다음 머리 전까지(카드는 쪽을 넘지 않음)
            mem = [l for l in lines if col_pred(l) and hd.Y - 30 <= l.Y < nxt - 30 and l.p == hd.p and l is not hd]
            res.append((hd, mem))
        return res

    for hd, mem in group(rd_heads, lambda l: l.x >= 210):
        mem = [l for l in mem if l.Y > hd.Y]
        tag = next((l.t for l in mem if l.s == 7.0 and l.c in ACCENTS), "")
        title = next((l.t for l in mem if l.s == 10.0), "")
        body_lines = [l for l in mem if not (l.s == 7.0 and l.c in ACCENTS) and l.s != 10.0]
        rd.append({"tag": tag, "title": title, "html": flow_html(body_lines, accent)})
    for hd, mem in group(lg_heads, lambda l: l.x < 210):
        num = next((l.t for l in mem if l.s == 20.0 and l.Y < hd.Y), "")
        after = [l for l in mem if l.Y > hd.Y and l.s != 20.0]
        title = after[0].t if after else ""
        k = 1
        while k < len(after) and ((after[k].c == after[0].c and after[k].s == after[0].s) or (after[k].c == "59627a" and HAN.match(after[k].t))) and after[k].Y - after[k - 1].Y < 20:
            title += glue(title, after[k].t) + after[k].t
            k += 1
        body = ""
        for l in after[k:]:
            body += (glue(body, l.t) if body else "") + l.t
        lg.append({"n": num, "title": title, "body": body})
    return rd, lg


# ───────────── 처방 하나 ─────────────
def parse_formula(lines, start_page, end_page, accent):
    L = [l for l in lines if start_page <= l.p < end_page and not is_chrome(l)]
    cover = [l for l in L if l.p == start_page]
    eb = [l for l in L if l.s == 6.9 and l.t.replace(" ", "") in EYEBROWS]
    eb.sort(key=lambda l: l.Y)
    f = {}
    num = next(l for l in cover if l.s >= 30)
    f["id"] = num.t.strip()
    name = next(l for l in cover if l.s == 25.0).t.strip()
    m = re.match(r"^([가-힣0-9·\s]+?)([\u3400-\u9fff\uf900-\ufaff].*)$", name)
    f["ko"], f["hz"] = (m.group(1), m.group(2)) if m else (name, "")
    alias = [l.t for l in cover if l.s == 10.5 and l.c == "3d4760"]
    f["alias"] = alias[0] if alias else ""
    ms = next((l.t for l in cover if l.s == 10.0 and l.c == "3d4760" and l.y < 260), "")
    mm = re.match(r"^(.*?)\s*([\u3400-\u9fff].*)$", ms)
    f["master_ko"], f["master_hz"] = (mm.group(1).strip(), mm.group(2).strip()) if mm else (ms, "")
    id_y = next((l.Y for l in eb if EYEBROWS[l.t.replace(" ", "")] == "identity"), 10 ** 9)
    tag = [l for l in cover if l.s == 11.0 and l.c == "2e3850" and l.Y < id_y]
    t = ""
    for l in sorted(tag, key=lambda l: l.y):
        t += (glue(t, l.t) if t else "") + l.t
    f["tagline"] = t
    # 메타 3칸
    labels = sorted([l for l in cover if l.s == 6.8 and l.c == "6b7388" and l.Y < id_y], key=lambda l: l.x)
    meta = {}
    for k, lb in enumerate(labels):
        x0 = lb.x - 6
        x1 = labels[k + 1].x - 6 if k + 1 < len(labels) else 999
        vals = sorted([l for l in cover if lb.y < l.y < lb.y + 40 and x0 <= l.x < x1 and l is not lb and l.Y < id_y], key=lambda l: (l.y, l.x))
        v = ""
        for l in vals:
            v += (glue(v, l.t) if v else "") + l.t
        meta[lb.t] = v
    f["meta"] = meta
    f["page"] = start_page + 1
    # 절 나누기
    secs = []
    for k, e in enumerate(eb):
        key = EYEBROWS[e.t.replace(" ", "")]
        nxt = eb[k + 1].Y if k + 1 < len(eb) else 10 ** 9
        title = next((l.t for l in L if l.s == 13.0 and 0 < l.Y - e.Y < 25), "")
        mem = [l for l in L if e.Y + 4 < l.Y < nxt - 6 and not (l.s == 13.0 and abs(l.Y - e.Y) < 25)
               and not (l.c == "ffffff" and l.s == 9.0 and l.x < 70)]
        if key == "identity":
            mem = [l for l in mem if l.p == e.p or True]
        secs.append([key, title, mem])
    f["sections"] = []
    for key, title, mem in secs:
        if key == "identity":
            f["identity"] = parse_identity(mem, accent)
            continue
        if key == "composition":
            f["modules"], rest = parse_modules(mem, accent)
            f["sections"].append({"k": key, "t": title, "html": flow_html(rest, accent)})
            continue
        if key == "rd":
            rd, lg = cards_html(mem, accent)
            card_lines = set()
            f["rd"] = rd
            f["logic"] = lg
            f["sections"].append({"k": key, "t": title, "html": ""})
            continue
        if key == "china":
            f["sections"].append({"k": key, "t": title, "html": flow_html(mem, accent)})
            continue
        f["sections"].append({"k": key, "t": title, "html": flow_html(mem, accent)})
    return f


def parse_identity(mem, accent):
    labs = sorted([l for l in mem if l.s == 8.0 and l.c in ACCENTS and l.x < 100], key=lambda l: l.Y)
    out = {"herbs": [], "notes": []}
    for k, lb in enumerate(labs):
        nxt = labs[k + 1].Y - 4 if k + 1 < len(labs) else 10 ** 9
        vals = sorted([l for l in mem if l.x > 120 and lb.Y - 4 <= l.Y < nxt], key=lambda l: (l.Y, l.x))
        name = lb.t.strip()
        if name == "조성":
            for v in vals:
                if v.t.startswith("※") or (v.s <= 8.0 and v.c == "6b7388"):
                    out["notes"].append(v.t)
                else:
                    out["herbs"].append(herb_parse(v.t))
            continue
        items, cur = [], ""
        for v in vals:
            if v.t.lstrip().startswith("•"):
                if cur:
                    items.append(cur)
                cur = v.t.lstrip("• ").strip()
            else:
                cur += (glue(cur, v.t) if cur else "") + v.t
        if cur:
            items.append(cur)
        out[name] = items
    return out


def herb_parse(t):
    t = t.strip()
    m = re.match(r"^(.*?)(\d[\d.~\-–]*\s*(?:g|mg|ml|mL|kg|개|枚|매|條|조|片|편|只|마리|錢|돈)?(?:\s*\([^)]*\))?)$", t)
    name, dose = (m.group(1).strip(), m.group(2).strip()) if m and m.group(1) else (t, "")
    base = re.sub(r"\([^)]*\)", "", name)
    base = re.sub(r"[\u3400-\u9fff\uf900-\ufaff]+$", "", base)          # 뒤 한자 병기
    base = re.sub(r"^[\u3400-\u9fff\uf900-\ufaff]+", "", base).strip()  # 앞 가공·산지 한자
    return {"raw": t, "name": name, "dose": dose, "base": base or name}


def parse_modules(mem, accent):
    """처방 구성 표(모듈·구성 약재·역할) + 나머지 줄"""
    hdr = [l for l in mem if l.s == 7.4 and l.c == "6b7388" and l.t in ("모듈", "구성 약재", "역할")]
    if len(hdr) < 3:
        return [], mem
    hy = min(l.Y for l in hdr)
    cap = next((l for l in mem if l.t.startswith("그림") and l.Y > hy), None)
    end = cap.Y if cap else hy + 400
    xs = sorted(l.x for l in hdr)
    region = [l for l in mem if hy - 3 <= l.Y < end - 2]
    names = sorted([l for l in region if l.c == "ffffff" and l.s >= 9.5 and re.match(r"^[①-⑩]", l.t)], key=lambda l: l.Y)
    mods = []
    for k, nm in enumerate(names):
        y0 = nm.Y - 8
        y1 = names[k + 1].Y - 8 if k + 1 < len(names) else end
        cell = [l for l in region if y0 <= l.Y < y1 and l is not nm]
        sub = [l.t for l in sorted(cell, key=lambda l: l.Y) if l.c == "ffffff" and l.x < xs[1] - 30 and l.s >= 8.9 and not HAN.match(l.t[0])]
        hz = [l.t for l in sorted(cell, key=lambda l: l.Y) if l.c == "ffffff" and HAN.match(l.t[0])]
        herbs = [l.t for l in sorted(cell, key=lambda l: (l.Y, l.x)) if xs[1] - 10 <= l.x < xs[2] - 5 and l.c != "ffffff"]
        role = ""
        for l in sorted([l for l in cell if l.x >= xs[2] - 5 and l.c != "ffffff"], key=lambda l: l.Y):
            role += (glue(role, l.t) if role else "") + l.t
        mods.append({"name": " · ".join([nm.t] + sub), "hz": " · ".join(hz), "herbs": herbs, "role": role})
    rest = [l for l in mem if not (hy - 3 <= l.Y < end - 2)]
    return mods, rest


# ───────────── 앞부분: 비교표·분야 ─────────────
def parse_compare(lines):
    rows = []
    for p in range(3, 7):
        P = [l for l in lines if l.p == p and not is_chrome(l)]
        nos = sorted([l for l in P if re.fullmatch(r"\d-\d{1,2}", l.t.strip()) and l.x < 70], key=lambda l: l.y)
        for k, no in enumerate(nos):
            y1 = nos[k + 1].y - 3 if k + 1 < len(nos) else no.y + 28
            cell = [l for l in P if no.y - 3 <= l.y < y1]

            def col(x0, x1):
                v = ""
                for l in sorted([l for l in cell if x0 <= l.x < x1], key=lambda l: (l.y, l.x)):
                    v += (glue(v, l.t) if v else "") + l.t
                return v
            rows.append({"id": no.t.strip(), "evidence": col(340, 425), "product": col(425, 515)})
    return {r["id"]: r for r in rows}


def parse_status(lines):
    """그림 B(처방별 중국 제품화 단계) — 칩 배경색으로 단계 판정"""
    import pymupdf
    d = pymupdf.open(os.environ.get("GUOYI_PDF", r"D:\학습자료\도서 및 자료\중국_국의대사_경험방_RD인사이트_전자책.pdf"))
    pg = d[2]
    rects = []
    for dr in pg.get_drawings():
        if dr.get("fill") is not None:
            rects.append((pymupdf.Rect(dr["rect"]), tuple(round(c, 3) for c in dr["fill"])))
    P = [l for l in lines if l.p == 2]
    legend = ["허가 중성약", "원내제제·연구용 제제", "특허 출원 이력", "확인된 제품·특허 없음", "동명 제품(조성 미확인)"]
    colmap = {}
    for lg in legend:
        l = next((x for x in P if x.t.strip() == lg), None)
        if not l:
            continue
        cands = [(r, c) for r, c in rects if r.width < 16 and r.height < 16 and abs((r.y0 + r.y1) / 2 - (l.y + l.y2) / 2) < 6 and r.x1 <= l.x + 2 and l.x - r.x1 < 20]
        if cands:
            colmap[cands[-1][1]] = lg
    st = {}
    for l in P:
        if re.fullmatch(r"\d-\d{1,2}", l.t.strip()) and l.y > 330:
            cx, cy = (l.x + l.x2) / 2, (l.y + l.y2) / 2
            box = [(r, c) for r, c in rects if r.contains(pymupdf.Point(cx, cy)) and r.width < 120 and r.height < 60]
            box.sort(key=lambda rc: rc[0].width * rc[0].height)
            for r, c in box:
                if c in colmap:
                    st[l.t.strip()] = colmap[c]
                    break
    return st, legend


def parse_fields(lines):
    fields = {}
    for p in (11, 82, 157, 214, 259):
        P = [l for l in lines if l.p == p]
        t = max(P, key=lambda l: l.s if HANGUL.search(l.t) else 0)
        nm = re.match(r"^0?(\d)", next(l.t for l in P if re.fullmatch(r"0\d", l.t.strip())))
        fields[int(nm.group(1))] = {"name": t.t.strip(), "page": p + 1}
    return fields


def front_flow(lines, pages, accent="1f7a6c"):
    mem = [l for l in lines if l.p in pages and not is_chrome(l) and not (l.s == 6.9 or l.s >= 13)]
    return flow_html(mem, accent)


def build():
    lines = load()
    starts = sorted({l.p for l in lines if l.s >= 30 and re.fullmatch(r"\d-\d{1,2}", l.t.strip())})
    ends = starts[1:] + [335]
    fields = parse_fields(lines)
    # 분야 칸막이 쪽은 처방 범위에서 뺀다
    dividers = {v["page"] - 1 for v in fields.values()}
    cmp = parse_compare(lines)
    status, legend = parse_status(lines)
    formulas = []
    for s, e in zip(starts, ends):
        e2 = min([x for x in dividers if s < x < e] + [e])
        num = next(l for l in lines if l.p == s and l.s >= 30)
        accent = num.c
        f = parse_formula(lines, s, e2, accent)
        f["field"] = ACCENTS.get(accent, int(f["id"].split("-")[0]))
        f["pages"] = [s + 1, e2]
        c = cmp.get(f["id"], {})
        f["evidence"] = c.get("evidence", f["meta"].get("확인된 연구자료 유형", ""))
        f["product"] = c.get("product", f["meta"].get("제형·제품화", ""))
        f["status"] = status.get(f["id"], "확인된 제품·특허 없음")
        formulas.append(f)
    # 앞뒤 부분
    front = {
        "foreword": front_flow(lines, [1]),
        "howto": front_flow(lines, [7]),
        "abbr": front_flow(lines, list(range(335, 340))),
        "colophon": front_flow(lines, [340]),
    }
    return {"fields": fields, "formulas": formulas, "front": front, "legend": legend}


if __name__ == "__main__":
    D = build()
    print(len(D["formulas"]), "formulas")
    for f in D["formulas"][:3] + D["formulas"][-2:]:
        print(f["id"], f["ko"], f["hz"], f["master_ko"], f["master_hz"], f["meta"], f["status"], f["pages"])
        print("  herbs", [h["raw"] for h in f["identity"]["herbs"]][:20])
        print("  idkeys", list(f["identity"].keys()))
        print("  modules", [(m["name"], m["hz"], m["herbs"], m["role"][:30]) for m in f.get("modules", [])])
        print("  rd", [(c["tag"], c["title"]) for c in f.get("rd", [])])
        print("  logic", [(c["n"], c["title"], c["body"][:40]) for c in f.get("logic", [])])
        print("  secs", [(s["k"], s["t"], len(s["html"])) for s in f["sections"]])
    json.dump(D, open(os.path.join(HERE, "guoyi.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
