# -*- coding: utf-8 -*-
"""PDF 텍스트 층 → 줄 목록(쪽, 좌표, 크기, 색, 글) JSON. 양식 분류의 원재료."""
import json, os, sys
import pymupdf
PDF = os.environ.get("GUOYI_PDF", r"D:\학습자료\도서 및 자료\중국_국의대사_경험방_RD인사이트_전자책.pdf")
out = []
d = pymupdf.open(PDF)
for i in range(d.page_count):
    for b in d[i].get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            t = "".join(s["text"] for s in l["spans"])
            if not t.strip():
                continue
            mx = max(x["size"] for x in l["spans"] if x["text"].strip())
            s = next(x for x in l["spans"] if x["text"].strip() and x["size"] >= 0.85 * mx)  # 줄머리 위첨자([7] 등) 건너뜀
            bold = any(("Bold" in x["font"]) or (x["flags"] & 16) for x in l["spans"])
            out.append([i, round(l["bbox"][0], 1), round(l["bbox"][1], 1), round(l["bbox"][2], 1), round(l["bbox"][3], 1),
                        round(s["size"], 1), "%06x" % s["color"], t])
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lines.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(len(out), "lines")
