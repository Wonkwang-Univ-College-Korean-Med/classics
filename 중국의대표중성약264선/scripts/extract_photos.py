# -*- coding: utf-8 -*-
"""PDF 1~568쪽의 제품 포장 사진을 쪽·위치 순으로 뽑아 images/zcy264/pNNNN_k.jpg로 저장한다."""
import io, json, os, sys
import pymupdf
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.environ.get("ZCY264_PDF", r"D:\학습자료\도서 및 자료\『중국의 대표 중성약 264선』 최종.pdf")
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "images", "zcy264")
d = pymupdf.open(PDF); meta = {}
for i in range(1, 569):
    p = d[i]; items = []
    for info in p.get_image_info(xrefs=True):
        x = info.get("xref"); bb = pymupdf.Rect(info["bbox"])
        if not x or bb.width < 80 or bb.height < 50: continue
        items.append((bb.y0, bb.x0, x, bb))
    items.sort()
    for k, (_, _, x, bb) in enumerate(items):
        # 사진이 놓인 영역을 그대로 렌더링(마스크·색공간 문제 회피)
        pix = p.get_pixmap(dpi=150, clip=bb)
        im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        im.thumbnail((480, 360))
        name = f"p{i:04d}_{k+1}.jpg"
        im.save(os.path.join(OUT, name), quality=78, optimize=True)
        meta.setdefault(f"{i:04d}", []).append({"file": name, "y": round(bb.y0, 1)})
json.dump(meta, open(os.path.join(HERE, "photos.json"), "w", encoding="utf-8"), indent=0)
print("pages with photos:", len(meta), "photos:", sum(len(v) for v in meta.values()))
