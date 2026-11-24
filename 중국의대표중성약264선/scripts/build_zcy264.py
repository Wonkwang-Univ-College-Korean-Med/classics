# -*- coding: utf-8 -*-
"""ocr_pages/pNNNN.md(Claude 비전 OCR 결과) → 『중국의 대표 중성약 264選』 대화형 전자책.

    python build_zcy264.py                 # 로컬 열람본(중국의대표중성약264선/중국의대표중성약264선.html) + 통합 .md + 점검 보고
    python build_zcy264.py --web           # classics 루트 zhongchengyao-264.html · zhongchengyao-264/index.html 도 생성
    python build_zcy264.py --check         # 점검만

쪽 번호: PDF 1~568쪽 = 인쇄 쪽 번호(1번째 사본). 2·3번째 사본은 같은 쪽이라 쓰지 않는다.
"""
import argparse
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # 중국의대표중성약264선/
REPO = os.path.dirname(ROOT)                       # classics/
OCR = os.path.join(ROOT, "ocr_pages")
SLUG = "zhongchengyao-264"
TITLE = "중국의 대표 중성약 264選"

FIELD_ORDER = ["제형", "처방유형", "규격", "조성", "기능 및 주치", "처방해설", "임상응용", "약리독리", "약리작용",
               "불량반응", "금기", "주의사항", "용법용량", "제조사", "개발사", "연구동향"]
SUPD = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
SUP_CH = "⁰¹²³⁴⁵⁶⁷⁸⁹"


# ───────────────────────── 쪽 읽기 ─────────────────────────
def load_pages():
    P = {}
    for f in os.listdir(OCR):
        m = re.fullmatch(r"p(\d{4})\.md", f)
        if m:
            P[int(m.group(1))] = open(os.path.join(OCR, f), encoding="utf-8").read()
    return P


def split_page(txt):
    """쪽 → (본문 줄 목록, 쪽 아래 각주 {번호: 글})"""
    txt = re.sub(r"^<!--\s*page:.*?-->\s*\n?", "", txt.strip())
    notes = {}
    m = re.search(r"\n-{3,}\s*\n((?:\s*\d+\).*\n?)+)\s*$", "\n" + txt + "\n")
    if m:
        body = ("\n" + txt + "\n")[: m.start()]
        cur = None
        for ln in m.group(1).splitlines():
            mm = re.match(r"\s*(\d+)\)\s*(.*)", ln)
            if mm:
                cur = int(mm.group(1)); notes[cur] = mm.group(2).strip()
            elif cur and ln.strip():
                notes[cur] += " " + ln.strip()
        txt = body
    lines = [ln.rstrip() for ln in txt.strip("\n").splitlines()]
    return lines, notes


# ───────────────────── 쪽 경계 잇기 ─────────────────────
HANG = re.compile(r"[가-힣]")
CJK = re.compile(r"[㐀-鿿豈-﫿]")
STRUCT = re.compile(r"^\s*(#|- \*\*|\||\[제품사진|> |>$|\d+\)\s|\(\d+\)\s|[⑴-⒇]|\*\*제\d)")


class Joiner:
    def __init__(self, corpus):
        self.corpus = corpus

    def glue(self, a, b):
        """앞 쪽 마지막 줄 a 와 다음 쪽 첫 조각 b 를 잇는 문자열(공백 또는 '')"""
        if not a or not b:
            return ""
        x, y = a[-1], b[0]
        if CJK.match(x) and CJK.match(y):
            return ""
        if x in ",.;:·)]」》’”" or y in "([「《‘“":
            return " " if x in ",.;:)]」》’”" else ""
        if (HANG.match(x) or CJK.match(x)) and HANG.match(y):
            if CJK.match(x):           # 한자 뒤 한글: 대부분 '辛溫하며' 같은 붙임
                return ""
            lt = re.split(r"[\s,.;:()]", a)[-1]
            ft = re.split(r"[\s,.;:()]", b)[0]
            # ① 한자 병기: '신|고온조辛苦溫燥' — 한글이 한자보다 짧으면 모자란 글자가 앞 쪽 끝에 있다
            m = re.match(r"([가-힣]+)([㐀-鿿豈-﫿]+)", ft)
            tail = re.search(r"[가-힣]+$", lt)
            if m and tail and 0 < len(m.group(2)) - len(m.group(1)) <= len(tail.group(0)):
                return ""
            # ② 말뭉치에서 붙여 쓴 꼴과 띄어 쓴 꼴의 빈도 비교
            x, y = lt[-2:], re.match(r"[가-힣]*", ft).group(0)[:2]
            if x and y:
                c1 = self.corpus.count(x + y)
                c2 = self.corpus.count(x + " " + y)
                return "" if c1 > c2 else " "
            return " "
        return " " if (x.isalnum() and y.isalnum()) else ""


def stream(P, pages, joiner):
    """여러 쪽을 하나의 줄 목록으로 잇는다. 줄마다 (쪽, 글) 쌍. 쪽 각주 표지는 ¹⁾ → ‹fn:쪽:번호›."""
    out = []
    prev_table_head = None
    for i in pages:
        lines, notes = split_page(P[i])
        # 쪽 각주 참조 표지 바꾸기(본문 위첨자 숫자 + ')')
        def fnrep(m):
            n = int(m.group(1).translate(SUPD))
            return f"‹fn:{i}:{n}›" if n in notes else m.group(0)
        lines = [re.sub(r"([" + SUP_CH + r"]+)\)", fnrep, ln) for ln in lines]
        out_notes = {n: t for n, t in notes.items()}
        # 앞 쪽에서 이어진 표의 반복 머리줄 지우기
        if prev_table_head and len(lines) >= 2 and lines[0].startswith("|") and lines[0] == prev_table_head \
                and re.match(r"^\|[-\s|:]+\|$", lines[1]):
            lines = lines[2:]
        first = next((k for k, ln in enumerate(lines) if ln.strip()), None)
        if first is not None and out:
            ln = lines[first]
            cand = [k for k, (_, t) in enumerate(out) if t.strip() and not t.startswith("‹note:")]
            last_k = cand[-1] if cand else None
            if last_k is not None:
                lp, lt = out[last_k]
                cont = False
                if not STRUCT.match(ln) and not ln.lstrip().startswith("- ") and not lt.startswith("|") \
                        and not lt.lstrip().startswith("#") \
                        and not (not lt.startswith((" ", "-", ">")) and re.search(r"[.。]$", lt.rstrip())):
                    cont = True                                   # 맨 글줄 → 앞 문단에 잇기(문단 끝 마침표면 새 문단)
                elif ln.startswith("  - ") and not lt.lstrip().startswith(("#", "|", ">")):
                    tail = lt.rstrip()
                    if tail and (tail[-1] in ",;·(、" or (len(tail) > 38 and not re.search(r"[.。)\]⁾다]$", tail)
                                                           and " : " not in ln[:20])):
                        cont = True
                        ln = ln[4:]
                if cont:
                    piece = ln.strip()
                    out[last_k] = (lp, lt.rstrip() + joiner.glue(lt.rstrip(), piece) + piece)
                    lines = lines[first + 1:]
        for ln in lines:
            out.append((i, ln))
        for n, t in out_notes.items():
            out.append((i, f"‹note:{i}:{n}›{t}"))
        th = [ln for ln in lines if ln.startswith("|")]
        prev_table_head = None
        if th:
            # 이 쪽 표의 머리줄(첫 줄) 기억
            for k, ln in enumerate(lines):
                if ln.startswith("|") and k + 1 < len(lines) and re.match(r"^\|[-\s|:]+\|$", lines[k + 1]):
                    prev_table_head = ln
                    break
            if lines and not lines[-1].startswith("|") and not any(l.startswith("|") for l in lines[-3:]):
                prev_table_head = None
    return out


# ───────────────────── 마크다운 → HTML (이 책에 필요한 만큼) ─────────────────────
def inline(s, refs=None, notes=None):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", s)

    def fn(m):
        p, n = int(m.group(1)), int(m.group(2))
        t = (notes or {}).get((p, n), "")
        return f'<sup class="fn" tabindex="0" data-t="{html.escape(t)}">{n})</sup>'
    s = re.sub(r"‹fn:(\d+):(\d+)›", fn, s)

    def rf(m):
        nums = re.findall(r"\d+", m.group(1).translate(SUPD))
        parts = []
        for n in nums:
            t = (refs or {}).get(int(n), "")
            parts.append(f'<sup class="rf" tabindex="0" data-t="{html.escape(t)}">[{n}]</sup>')
        return "".join(parts)
    s = re.sub(r"⁽([" + SUP_CH + r"⁻,˒‚·\s]+)⁾", rf, s)
    return s


def md_to_html(lines, refs=None, notes=None, hid=None):
    """lines: 글 목록. 목록(들여쓰기 2칸 단위)·표·인용·제목·문단."""
    out = []
    stack = []        # 열린 ul 들여쓰기 수준
    para = []
    i = 0

    def close_lists(level=-1):
        while stack and stack[-1] > level:
            out.append("</li></ul>"); stack.pop()

    def flush_para():
        if para:
            out.append("<p>" + "<br>".join(inline(p, refs, notes) for p in para) + "</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            flush_para(); i += 1; continue
        if ln.startswith("‹note:"):
            i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            flush_para(); close_lists()
            lv = min(len(m.group(1)) + 1, 6)
            idattr = f' id="{hid(m.group(2))}"' if hid else ""
            out.append(f"<h{lv}{idattr}>{inline(m.group(2), refs, notes)}</h{lv}>")
            i += 1; continue
        if ln.lstrip().startswith("|"):
            flush_para(); close_lists()
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i].strip()); i += 1
            out.append(table_html(rows, refs, notes))
            continue
        if re.match(r"^\s*>", ln):
            flush_para()
            q = []
            while i < len(lines) and re.match(r"^\s*>", lines[i]):
                q.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
            body = []
            for t in q:
                mm = re.match(r"\[(\d+)\]\s*(.*)", t)
                if mm:
                    body.append(f'<div class="ref" data-n="{mm.group(1)}">[{mm.group(1)}] {inline(mm.group(2))}</div>')
                elif t.strip():
                    body.append(f"<div>{inline(t, refs, notes)}</div>")
            cls = "refs" if all('class="ref"' in b for b in body) else "quote"
            html_q = f'<blockquote class="{cls}">' + "".join(body) + "</blockquote>"
            if stack:
                out.append(html_q)
            else:
                out.append(html_q)
            continue
        m = re.match(r"^(\s*)-(?: |(?=[《“「]))(.*)$", ln)
        if m:
            flush_para()
            lv = len(m.group(1)) // 2
            if not stack or lv > stack[-1]:
                out.append("<ul><li>"); stack.append(lv)
            else:
                close_lists(lv)
                if stack and stack[-1] == lv:
                    out.append("</li><li>")
                else:
                    out.append("<ul><li>"); stack.append(lv)
            out.append(inline(m.group(2), refs, notes))
            i += 1; continue
        if stack and ln.startswith("  "):
            out.append("<br>" + inline(ln.strip(), refs, notes)); i += 1; continue
        close_lists()
        para.append(ln.strip()); i += 1
    flush_para(); close_lists()
    return "".join(out)


def table_html(rows, refs=None, notes=None):
    cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
    head = None
    if len(cells) >= 2 and all(re.fullmatch(r":?-{2,}:?", c) or c == "" for c in cells[1]):
        head, cells = cells[0], cells[2:]
    h = ['<div class="tbl"><table>']
    if head:
        h.append("<thead><tr>" + "".join(f"<th>{inline(c, refs, notes)}</th>" for c in head) + "</tr></thead>")
    h.append("<tbody>")
    for r in cells:
        h.append("<tr>" + "".join(f"<td>{inline(c, refs, notes)}</td>" for c in r) + "</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


def plain(s):
    s = re.sub(r"‹fn:\d+:\d+›", "", s)
    s = re.sub(r"⁽[^⁾]*⁾", "", s)
    s = s.replace("**", "")
    return re.sub(r"\s+", " ", s).strip()


# ───────────────────── 2장 약물 파싱 ─────────────────────
def split_name(s):
    s = s.strip()
    m = re.match(r"^([가-힣0-9·\s]+?)\s*([㐀-鿿豈-﫿].*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return s, ""


HERB_PREFIX = re.compile(r"^[焦炒制製醋炙酒蜜煅煨麸麩鹽盐姜薑生熟淨净法]+")


def herbs_of(txt):
    t = plain(txt)
    t = re.sub(r"\([^)]*\)|（[^）]*）", "", t)
    out = []
    for tok in re.split(r"[,，、;；]|\s및\s|\s와\s", t):
        tok = tok.strip(" .·")
        tok = HERB_PREFIX.sub("", tok).strip()
        tok = re.sub(r"\s*\d.*$", "", tok)        # 용량·함량 꼬리
        if 1 <= len(tok) <= 12 and not re.search(r"[:：]", tok):
            out.append(tok)
    return out


def parse_drugs(lines, notes):
    tree = []            # 분과 > 효능군 > 세부
    drugs = []
    cur = {"sec": None, "grp": None, "sub": None}
    d = None
    field = None

    def node(level, title):
        n = {"t": title, "c": [], "d": []}
        if level == 2:
            tree.append(n); cur.update(sec=n, grp=None, sub=None)
        elif level == 3:
            (cur["sec"]["c"] if cur["sec"] else tree).append(n); cur.update(grp=n, sub=None)
        else:
            parent = cur["grp"] or cur["sec"]
            parent["c"].append(n); cur.update(sub=n)
        return n

    for p, ln in lines:
        if ln.startswith("‹note:"):
            continue
        m = re.match(r"^(#{1,5})\s+(.*)$", ln)
        if m:
            lv = len(m.group(1)); title = m.group(2).strip()
            if lv == 1:
                continue
            if lv in (2, 3, 4):
                node(lv, re.sub(r"‹fn:\d+:\d+›", "", title)); d = None; field = None
                continue
            mm = re.match(r"\((\d+)\)\s*(.*)", title)
            if mm:
                ko, hz = split_name(mm.group(2))
                d = {"n": int(mm.group(1)), "ko": ko, "hz": hz, "page": p, "pages": [p], "pre": [], "fields": [],
                     "sec": cur["sec"]["t"] if cur["sec"] else "", "grp": cur["grp"]["t"] if cur["grp"] else "",
                     "sub": cur["sub"]["t"] if cur["sub"] else "", "photo_tags": []}
                drugs.append(d)
                (cur["sub"] or cur["grp"] or cur["sec"])["d"].append(len(drugs) - 1)
                field = None
            continue
        if d is None:
            continue
        if p not in d["pages"]:
            d["pages"].append(p)
        mm = re.match(r"^\[제품사진:\s*(.*?)\]$", ln.strip())
        if mm:
            d["photo_tags"].append((p, mm.group(1))); continue
        mm = re.match(r"^- \*\*(.+?)\*\*\s*[:：]?\s*(.*)$", ln) or \
            re.match(r"^\s+- \*\*(" + "|".join(map(re.escape, FIELD_ORDER)) + r")\*\*\s*[:：]?\s*(.*)$", ln)
        if mm:
            field = [mm.group(1).strip().rstrip(":："), []]
            if mm.group(2).strip():
                field[1].append(mm.group(2).strip())
            d["fields"].append(field)
            continue
        if field is None:
            d["pre"].append(ln); continue
        if ln.startswith("  "):
            field[1].append(ln[2:])
        elif ln.strip():
            field[1].append(ln)
        else:
            field[1].append("")
    return tree, drugs


# ───────────────────── 부록 표 ─────────────────────
def parse_appx1(lines):
    rows, cat = [], {}
    for _, ln in lines:
        if not ln.startswith("|") or re.match(r"^\|[-\s|:]+\|$", ln) or "약품분류코드" in ln:
            continue
        c = [x.strip().replace("**", "") for x in ln.strip("|").split("|")]
        c += [""] * (5 - len(c))
        code, catn, grade, no, name = c[:5]
        if code and catn and not name:
            depth = len(code) - 1 if len(code) <= 3 else (3 if len(code) <= 5 else 4)
            rows.append({"k": "c", "code": code, "t": catn, "lv": min(len(code) // 2, 3)})
        elif name:
            rows.append({"k": "r", "g": grade, "no": no, "t": name})
    return rows


def parse_appx2(lines):
    items = {}
    for _, ln in lines:
        if not ln.startswith("|") or re.match(r"^\|[-\s|:]+\|$", ln) or "약명" in ln:
            continue
        c = [x.strip() for x in ln.strip("|").split("|")]
        for k in range(0, len(c) - 1, 2):
            if re.fullmatch(r"\d+", c[k] or "") and c[k + 1]:
                items[int(c[k])] = c[k + 1]
    return [[k, items[k]] for k in sorted(items)]


def parse_index(P):
    idx = {}
    for i in range(564, 568):
        for ln in P[i].splitlines():
            m = re.match(r"^-\s*(.+?)\s*…\s*(\d{3})\s*$", ln)
            if m:
                idx[re.sub(r"\s", "", m.group(1))] = int(m.group(2))
    return idx


# ───────────────────── 조립 ─────────────────────
def build():
    P = load_pages()
    missing = [i for i in range(1, 569) if i not in P]
    if missing:
        sys.exit(f"OCR 쪽 없음: {missing[:20]}")
    corpus = "\n".join(P[i] for i in range(1, 569))
    J = Joiner(corpus)

    photos = json.load(open(os.path.join(HERE, "photos.json"), encoding="utf-8"))
    report = []

    # 앞부분
    front = []
    for title, pages in (("일러두기", [2]), ("발간사", [18, 19])):
        st = stream(P, pages, J)
        lines = [t for _, t in st]
        if lines and re.sub(r"[\s/]", "", lines[0]) in ("일러두기", "발간사", "중성약264선"):
            lines = [l for l in lines if re.sub(r"[\s/]", "", l) not in ("일러두기", "발간사", "중성약264선")]
        notes = _notes_of(st)
        front.append({"id": "f" + str(len(front)), "t": title, "page": pages[0], "html": md_to_html(lines, None, notes)})

    # 1장
    st1 = stream(P, list(range(22, 38)), J)
    notes1 = _notes_of(st1)
    hids = Counter()

    def hid(t):
        base = "c1-" + re.sub(r"[^0-9.]", "", t.split(" ")[0]).strip(".").replace(".", "-")
        if base == "c1-":
            base = "c1-x"
        hids[base] += 1
        return base if hids[base] == 1 else f"{base}-{hids[base]}"
    lines1 = [t for _, t in st1]
    # 1장 제목줄(# 01 …)은 화면 제목으로 대신
    lines1 = [l for l in lines1 if not re.match(r"^#\s+01\b", l)]
    ch1_html = md_to_html(lines1, None, notes1, hid)
    ch1_toc = [(int(m.group(1)) - 1, m.group(2), re.sub("<[^>]+>", "", m.group(3)))
               for m in re.finditer(r'<h(\d) id="([^"]+)">(.*?)</h\d>', ch1_html)]
    # 쪽 표시(1장): 각 h에 출처 쪽
    ch1_pages = {}
    for p, t in st1:
        m = re.match(r"^(#{2,3})\s+(\d[\d.]*)", t)
        if m:
            ch1_pages.setdefault(m.group(2).strip("."), p)

    # 2장
    st2 = stream(P, list(range(40, 504)), J)
    notes2 = _notes_of(st2)
    tree, drugs = parse_drugs(st2, notes2)
    report.append(f"약물 항목 {len(drugs)}개(번호 {len({d['n'] for d in drugs})}종)")

    # 사진 배정: 쪽의 사진을 그 쪽에서 시작하는 약물들에 순서대로
    starts = defaultdict(list)
    for k, d in enumerate(drugs):
        starts[f"{d['page']:04d}"].append(k)
    for pg, ph in photos.items():
        ks = [k for k in starts.get(pg, []) if not _is_xref(drugs[k])]
        if not ks:
            report.append(f"사진 쪽 {pg}: 시작 약물 없음"); continue
        if len(ks) == len(ph):
            for k, f in zip(ks, ph):
                drugs[k].setdefault("img", []).append(f["file"])
        else:
            for f in ph:
                drugs[ks[0]].setdefault("img", []).append(f["file"])

    # 약물별 필드 → HTML
    out_drugs = []
    herb_map = defaultdict(set)
    forms, rx = Counter(), Counter()
    for k, d in enumerate(drugs):
        refs = {}
        for _, body in d["fields"]:
            for ln in body:
                m = re.match(r"^\s*>\s*\[(\d+)\]\s*(.*)", ln)
                if m:
                    refs[int(m.group(1))] = plain(m.group(2))
        fl = []
        text = [d["ko"], d["hz"]]
        for name, body in d["fields"]:
            name = re.sub(r"\s+", " ", name)
            h = md_to_html(body, refs, notes2)
            fl.append([name, h])
            text.append(name + " " + " ".join(plain(b) for b in body if not b.lstrip().startswith(">")))
        fd = {n: b for n, b in d["fields"]}
        herbs = herbs_of(" ".join(fd.get("조성", []))) if "조성" in fd else []
        for hname in herbs:
            herb_map[hname].add(k)
        form = [x.strip() for x in re.split(r"[,，、]", plain(" ".join(fd.get("제형", [])))) if x.strip()]
        form = [re.sub(r"\s*[:(].*$", "", x) for x in form]
        for f in form:
            forms[f] += 1
        rxt = plain(" ".join(fd.get("처방유형", [])))
        rxk = []
        if "처방약" in rxt:
            rxk.append("처방약")
        if "OTC" in rxt.upper() or "비처방" in rxt:
            rxk.append("OTC")
        for r in rxk:
            rx[r] += 1
        pre = [l for l in d["pre"] if l.strip()]
        xref = None
        if pre and not d["fields"]:
            m = re.search(r"(\d{3})\s*페이지", " ".join(pre))
            xref = int(m.group(1)) if m else None
        out_drugs.append({
            "n": d["n"], "ko": d["ko"], "hz": d["hz"], "pg": d["page"], "pgs": d["pages"],
            "sec": d["sec"], "grp": d["grp"], "sub": d["sub"],
            "img": d.get("img", []), "f": fl, "herbs": herbs, "form": form, "rx": rxk,
            "pre": md_to_html(pre, refs, notes2) if pre else "", "xref": xref,
            "s": " ".join(text),
        })

    # 트리(약물 색인 번호)
    def tnode(n):
        return {"t": n["t"], "d": n["d"], "c": [tnode(c) for c in n["c"]]}
    tree = [tnode(n) for n in tree]

    # 부록·찾아보기
    st_a1 = stream(P, list(range(506, 544)), J)
    st_a2 = stream(P, list(range(544, 564)), J)
    a1 = parse_appx1(st_a1)
    a2 = parse_appx2(st_a2)
    report.append(f"부록1 행 {sum(1 for r in a1 if r['k'] == 'r')}개(분류 {sum(1 for r in a1 if r['k'] == 'c')}개) · 부록2 {len(a2)}종")
    idx = parse_index(P)

    # 점검: 찾아보기 ↔ 약물 제목 쪽
    real = [d for d in out_drugs if d["f"]]
    nums = Counter(d["n"] for d in real)
    report.append(f"본문 약물 {len(real)}개, 번호 1~264 누락 {[n for n in range(1, 265) if n not in nums]}, 중복 {[n for n, c in nums.items() if c > 1]}")
    byname = {re.sub(r"\s", "", d["ko"] + d["hz"]): d for d in real}
    mism = []
    for name, pg in idx.items():
        d = byname.get(name)
        if not d:
            mism.append(f"찾아보기에만: {name} {pg}")
        elif d["pg"] != pg:
            mism.append(f"쪽 다름: {name} 찾아보기 {pg} / 본문 {d['pg']}")
    for name, d in byname.items():
        if name not in idx:
            mism.append(f"본문에만: {name} {d['pg']}")
    report.append(f"찾아보기 {len(idx)}개 대조: 불일치 {len(mism)}건")
    report += ["  " + m for m in mism[:60]]
    nofield = [(d["n"], d["ko"]) for d in real if len(d["f"]) < 8]
    if nofield:
        report.append(f"항목 8개 미만 약물: {nofield}")
    noimg = [(d["n"], d["ko"]) for d in real if not d["img"]]
    if noimg:
        report.append(f"사진 없는 약물: {noimg}")
    labels = Counter(n for d in real for n, _ in d["f"])
    report.append("항목명 빈도: " + ", ".join(f"{k} {v}" for k, v in labels.most_common()))

    herbs = sorted(([h, sorted(v)] for h, v in herb_map.items()), key=lambda x: (-len(x[1]), x[0]))
    data = {
        "title": TITLE, "front": front,
        "ch1": {"html": ch1_html, "toc": ch1_toc, "pages": ch1_pages},
        "tree": tree, "drugs": out_drugs, "herbs": herbs,
        "forms": forms.most_common(), "rx": rx.most_common(),
        "a1": a1, "a2": a2,
    }
    # 통합 마크다운(검색·검수용)
    md = []
    for i in range(1, 569):
        md.append(P[i].strip())
    open(os.path.join(ROOT, "중국의대표중성약264선_OCR_전문.md"), "w", encoding="utf-8").write(
        f"# {TITLE} — OCR 전문 (한국한의학연구원, 2022)\n\n" +
        "> Claude 비전 OCR(claude-opus-5-5, 2026-11-24). 쪽마다 `<!-- page: NNN -->` 표지. PDF 1~568쪽.\n\n" +
        "\n\n".join(md) + "\n")
    return data, report


def _note(p, t):
    m = re.match(r"‹note:(\d+):(\d+)›(.*)", t)
    return (int(m.group(1)), int(m.group(2)), m.group(3)) if m else (p, 0, "")


def _notes_of(st):
    out = {}
    for p, t in st:
        m = re.match(r"‹note:(\d+):(\d+)›(.*)", t)
        if m:
            out[(int(m.group(1)), int(m.group(2)))] = m.group(3).strip()
    return out


def _is_xref(d):
    return not d["fields"]


# ───────────────────── HTML 쓰기 ─────────────────────
def render(data, base_img, web_rel=None):
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    auth = f'<script src="{web_rel}auth.js"></script>\n' if web_rel is not None else ""
    counter = ""
    if web_rel is not None:
        u = f"jaehyokim-sketch.github.io/classics/{SLUG}.html"
        counter = (f'<a class="hits" href="https://hits.sh/{u}/" target="_blank" rel="noopener noreferrer" title="Views 열람 횟수">'
                   f'<img src="https://hits.sh/{u}.svg?style=flat-square&label=%EC%A1%B0%ED%9A%8C%EC%88%98&color=2563eb&labelColor=0f172a" alt="Views"></a>')
    return (tpl.replace("<!--__AUTH__-->", auth).replace("<!--__COUNTER__-->", counter)
            .replace("__IMGBASE__", base_img).replace("/*__DATA__*/null", js))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    data, report = build()
    print("\n".join(report))
    if a.check:
        return
    local = os.path.join(ROOT, "중국의대표중성약264선.html")
    open(local, "w", encoding="utf-8").write(render(data, "../images/zcy264/"))
    print("로컬 열람본:", local, f"{os.path.getsize(local) / 1e6:.1f} MB")
    if a.web:
        p1 = os.path.join(REPO, f"{SLUG}.html")
        open(p1, "w", encoding="utf-8").write(render(data, "images/zcy264/", ""))
        os.makedirs(os.path.join(REPO, SLUG), exist_ok=True)
        p2 = os.path.join(REPO, SLUG, "index.html")
        open(p2, "w", encoding="utf-8").write(render(data, "../images/zcy264/", "../"))
        print("웹:", p1, p2)


if __name__ == "__main__":
    main()
