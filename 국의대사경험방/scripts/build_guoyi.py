# -*- coding: utf-8 -*-
"""『중국 국의대사 경험방 R&D 인사이트』 → 대화형 열람판.

    python extract_lines.py          # PDF → lines.json (한 번)
    python build_guoyi.py            # 로컬 열람본 + 통합 마크다운
    python build_guoyi.py --web      # classics 루트 guoyi-dashi.html · guoyi-dashi/index.html
"""
import argparse
import html
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import parse_guoyi as P  # noqa: E402

ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)
SLUG = "guoyi-dashi"


def width_paras(lines, right=520):
    """정렬된 본문: 줄 끝이 오른쪽 여백보다 많이 짧으면 문단 끝"""
    out, cur = [], ""
    for l in sorted(lines, key=lambda l: (l.p, l.y, l.x)):
        cur += (P.glue(cur, l.t) if cur else "") + l.t
        if l.x2 < right or l.t.endswith(("다.", "니다.")):
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def front(lines):
    L = [l for l in lines if not P.is_chrome(l)]
    # 발간사
    fw = [l for l in L if l.p == 1 and l.s >= 10 and l.s < 20]
    sig = [l.t for l in L if l.p == 1 and l.c == "6b7388" and l.s >= 9]
    foreword = "".join(f"<p>{P.esc(t)}</p>" for t in width_paras(fw)) + "".join(f'<p class="sig">{P.esc(t)}</p>' for t in sig)
    # 본문 읽는 법
    hw = [l for l in L if l.p == 7 and l.s < 20 and not (l.s <= 7.6 and l.c == "2747a0")]
    rows = P.rows_of(hw)
    items, notes, cur = [], [], None
    for r in rows:
        if len(r) >= 2:
            items.append((r[0].t, " ".join(c.t for c in r[1:])))
        elif r[0].t.startswith("※"):
            notes.append(r[0].t)
        elif notes and r[0].x > 60:
            notes[-1] += P.glue(notes[-1], r[0].t) + r[0].t
        elif items and r[0].s <= 9 and not r[0].t.startswith("읽을"):
            k, v = items[-1]
            items[-1] = (k, v + P.glue(v, r[0].t) + r[0].t)
    howto = '<dl class="dl">' + "".join(f"<dt>{P.esc(k)}</dt><dd>{P.esc(v)}</dd>" for k, v in items) + "</dl>"
    howto += "<h4>읽을 때 유의할 점</h4>" + "".join(f'<p class="note">{P.esc(n)}</p>' for n in notes)
    # 약어·척도 풀이
    ab = [l for l in L if 335 <= l.p <= 339 and l.s < 20 and not (l.s <= 7.6 and l.c == "2747a0")]
    groups, intro = [], []
    cur = None
    for r in P.rows_of(ab):
        if len(r) == 1 and r[0].s == 9.0 and r[0].c == "2747a0":
            cur = {"t": r[0].t, "rows": []}
            groups.append(cur)
            continue
        if r[0].c == "ffffff":
            continue
        if cur is None:
            intro.append(" ".join(c.t for c in r))
            continue
        cells = ["", "", ""]
        for c in r:
            k = 0 if c.x < 140 else (1 if c.x < 305 else 2)
            cells[k] += (P.glue(cells[k], c.t) if cells[k] else "") + c.t
        if cells[0] or not cur["rows"]:
            cur["rows"].append(cells)
        else:
            last = cur["rows"][-1]
            for k in range(3):
                if cells[k]:
                    last[k] += P.glue(last[k], cells[k]) + cells[k]
    intro_t = ""
    for t in intro:
        intro_t += (P.glue(intro_t, t) if intro_t else "") + t
    abbr = {"intro": intro_t, "groups": groups}
    # 발간 정보
    co = [l for l in L if l.p == 340]
    colophon = [(r[0].t, " ".join(c.t for c in r[1:])) for r in P.rows_of(co) if len(r) >= 2]
    return {"foreword": foreword, "howto": howto, "abbr": abbr, "colophon": colophon}


def plain(h):
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def build():
    lines = P.load()
    D = P.build()
    D["front"] = front(lines)
    for f in D["formulas"]:
        idt = f["identity"]
        txt = [f["id"], f["ko"], f["hz"], f["alias"], f["master_ko"], f["master_hz"], f["tagline"],
               " ".join(h["raw"] for h in idt["herbs"]), " ".join(idt.get("notes", []))]
        for k, v in idt.items():
            if k not in ("herbs", "notes"):
                txt.append(k + " " + " ".join(v))
        for m in f.get("modules", []):
            txt.append(" ".join([m["name"], m["hz"], " ".join(m["herbs"]), m["role"]]))
        for c in f.get("logic", []):
            txt.append(c["title"] + " " + c["body"])
        for c in f.get("rd", []):
            txt.append(c["tag"] + " " + c["title"] + " " + plain(c["html"]))
        secs = {}
        for s in f["sections"]:
            secs[s["k"]] = plain(s["html"])
        f["s"] = txt
        f["ss"] = secs
    return D


def to_md(D):
    out = ["# 중국 국의대사 경험방 R&D 인사이트 (한국한의학연구원, 2026)", "",
           "> PDF 텍스트 층에서 추출한 구조화 사본. 원서 쪽 번호는 각 처방 머리에 적음.", ""]
    for fid, fd in sorted(D["fields"].items(), key=lambda x: int(x[0])):
        out.append(f"## {fid}. {fd['name']}")
        for f in [f for f in D["formulas"] if f["field"] == int(fid)]:
            idt = f["identity"]
            out += ["", f"### {f['id']} {f['ko']}{f['hz']} — {f['master_ko']}{f['master_hz']} (원서 {f['pages'][0]}~{f['pages'][1]}쪽)", "",
                    f"*{f['tagline']}*", "",
                    f"- 주요 적응증: {f['meta'].get('주요 적응증', '')}",
                    f"- 확인된 연구자료 유형: {f['evidence']}",
                    f"- 제형·제품화: {f['product']} ({f['status']})",
                    f"- 조성: {', '.join(h['raw'] for h in idt['herbs'])}"]
            for n in idt.get("notes", []):
                out.append(f"  - {n}")
            for k, v in idt.items():
                if k in ("herbs", "notes"):
                    continue
                out.append(f"- {k}: " + (" / ".join(v)))
            if f.get("modules"):
                out += ["", "| 모듈 | 구성 약재 | 역할 |", "|---|---|---|"]
                for m in f["modules"]:
                    out.append(f"| {m['name']} ({m['hz']}) | {', '.join(m['herbs'])} | {m['role']} |")
            for s in f["sections"]:
                out += ["", f"#### {s['t']}", ""]
                if s["k"] == "rd":
                    for c in f.get("logic", []):
                        out.append(f"- 대사의 논리 {c['n']}. **{c['title']}** — {c['body']}")
                    for c in f.get("rd", []):
                        out.append(f"- R&D 제언 [{c['tag']}] **{c['title']}** — {plain(c['html'])}")
                else:
                    out.append(plain(s["html"]))
    return "\n".join(out) + "\n"


def render(D, web_rel=None):
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    js = json.dumps(D, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    auth = f'<script src="{web_rel}auth.js"></script>\n' if web_rel is not None else ""
    counter = ""
    if web_rel is not None:
        u = f"jaehyokim-sketch.github.io/classics/{SLUG}.html"
        counter = (f'<a class="hits" href="https://hits.sh/{u}/" target="_blank" rel="noopener noreferrer" title="Views 열람 횟수">'
                   f'<img src="https://hits.sh/{u}.svg?style=flat-square&label=%EC%A1%B0%ED%9A%8C%EC%88%98&color=2563eb&labelColor=0f172a" alt="Views"></a>')
    return tpl.replace("<!--__AUTH__-->", auth).replace("<!--__COUNTER__-->", counter).replace("/*__DATA__*/null", js)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", action="store_true")
    a = ap.parse_args()
    D = build()
    print(len(D["formulas"]), "처방")
    open(os.path.join(ROOT, "국의대사경험방_RD인사이트_전문.md"), "w", encoding="utf-8").write(to_md(D))
    local = os.path.join(ROOT, "국의대사경험방_RD인사이트.html")
    open(local, "w", encoding="utf-8").write(render(D))
    print("로컬:", local, f"{os.path.getsize(local) / 1e6:.1f} MB")
    if a.web:
        open(os.path.join(REPO, f"{SLUG}.html"), "w", encoding="utf-8").write(render(D, ""))
        os.makedirs(os.path.join(REPO, SLUG), exist_ok=True)
        open(os.path.join(REPO, SLUG, "index.html"), "w", encoding="utf-8").write(render(D, "../"))
        print("웹:", f"{SLUG}.html", f"{SLUG}/index.html")


if __name__ == "__main__":
    main()
