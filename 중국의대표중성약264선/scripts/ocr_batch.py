# -*- coding: utf-8 -*-
"""『중국의 대표 중성약 264選』 PDF → 쪽별 Markdown (Claude 비전 OCR, Message Batches API).

PDF는 글자가 윤곽선으로 바뀌어 텍스트 층이 없다. 쪽마다 위·아래 절반을 그림으로 보내
Claude가 한글·한자 혼용 본문을 옮겨 적게 한다(배치 API, 50% 할인).

    python ocr_batch.py submit  --pages pages.json [--model claude-opus-5-5]
    python ocr_batch.py status
    python ocr_batch.py collect          # 끝난 배치 결과를 ocr_pages/pNNNN.md로 저장
    python ocr_batch.py one 1708         # 한 쪽만 동기 호출(시험용)

API 키는 환경변수 ANTHROPIC_API_KEY로만 받는다(코드·파일에 쓰지 않는다).
"""
import argparse
import base64
import ctypes
import getpass
import json
import os
import sys

import pymupdf
import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "ocr_pages")
STATE = os.path.join(HERE, "batch_state.json")
PDF = os.environ.get("ZCY264_PDF", r"D:\학습자료\도서 및 자료\『중국의 대표 중성약 264선』 최종.pdf")
PROMPT = open(os.path.join(HERE, "ocr_prompt.md"), encoding="utf-8").read()
MODEL = "claude-opus-5-5"
MAX_BATCH_BYTES = 180 * 1024 * 1024


def _real_console():
    if not sys.stdin.isatty():
        return False
    if os.name != "nt":
        return True
    h = ctypes.windll.kernel32.GetStdHandle(-10)
    return bool(ctypes.windll.kernel32.GetConsoleMode(h, ctypes.byref(ctypes.c_uint())))


def client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        msg = "오류: 환경변수 ANTHROPIC_API_KEY가 없습니다."
        if _real_console():
            print(msg)
            os.environ["ANTHROPIC_API_KEY"] = getpass.getpass("Anthropic API 키를 입력하세요(화면에 표시되지 않음): ").strip()
        else:
            sys.exit(msg + ' PowerShell에서 $env:ANTHROPIC_API_KEY="<키>" 로 설정한 뒤 다시 실행하세요.')
    return anthropic.Anthropic()


def page_images(doc, i):
    p = doc[i]
    r = p.rect
    mid = r.height / 2
    out = []
    for clip in (pymupdf.Rect(0, 0, r.width, mid + 12), pymupdf.Rect(0, mid - 12, r.width, r.height)):
        z = 1568 / max(clip.width, clip.height)
        pix = p.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip)
        out.append(base64.standard_b64encode(pix.tobytes("png")).decode())
    return out


def params(doc, i, model):
    a, b = page_images(doc, i)
    content = [
        {"type": "text", "text": "[위 절반]"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": a}},
        {"type": "text", "text": "[아래 절반]"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b}},
        {"type": "text", "text": PROMPT},
    ]
    return dict(model=model, max_tokens=16000, output_config={"effort": "low"},
                messages=[{"role": "user", "content": content}])


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"batches": []}


def save_state(st):
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def text_of(msg):
    return "".join(b.text for b in msg.content if b.type == "text").strip() + "\n"


def cmd_submit(a):
    pages = json.load(open(a.pages, encoding="utf-8"))
    done = {f[1:5] for f in os.listdir(OUT) if f.endswith(".md")}
    pages = [i for i in pages if f"{i:04d}" not in done]
    if a.limit:
        pages = pages[: a.limit]
    print(f"제출할 쪽: {len(pages)}")
    cl = client()
    doc = pymupdf.open(PDF)
    st = load_state()
    chunk, size = [], 0

    def flush():
        nonlocal chunk, size
        if not chunk:
            return
        b = cl.messages.batches.create(requests=[r for r, _ in chunk])
        ids = [cid for _, cid in chunk]
        st["batches"].append({"id": b.id, "model": a.model, "pages": ids})
        save_state(st)
        print(f"  배치 {b.id}: {len(ids)}쪽 ({size / 1e6:.0f} MB)", flush=True)
        chunk, size = [], 0

    for i in pages:
        prm = params(doc, i, a.model)
        n = sum(len(c["source"]["data"]) for c in prm["messages"][0]["content"] if c["type"] == "image") + 8000
        if size + n > MAX_BATCH_BYTES or len(chunk) >= a.per_batch:
            flush()
        chunk.append((Request(custom_id=f"p{i:04d}", params=MessageCreateParamsNonStreaming(**prm)), f"p{i:04d}"))
        size += n
    flush()


def cmd_status(a):
    cl = client()
    for b in load_state()["batches"]:
        r = cl.messages.batches.retrieve(b["id"])
        c = r.request_counts
        print(b["id"], r.processing_status, f"ok={c.succeeded} err={c.errored} proc={c.processing} exp={c.expired}",
              b.get("collected", ""))


def cmd_collect(a):
    cl = client()
    st = load_state()
    usage = st.setdefault("usage", {"input": 0, "output": 0})
    bad = []
    for b in st["batches"]:
        if b.get("collected"):
            continue
        r = cl.messages.batches.retrieve(b["id"])
        if r.processing_status != "ended":
            print(b["id"], "아직 진행 중")
            continue
        n = 0
        for res in cl.messages.batches.results(b["id"]):
            if res.result.type == "succeeded":
                m = res.result.message
                usage["input"] += m.usage.input_tokens
                usage["output"] += m.usage.output_tokens
                if m.stop_reason != "end_turn":
                    bad.append((res.custom_id, m.stop_reason))
                open(os.path.join(OUT, res.custom_id + ".md"), "w", encoding="utf-8").write(text_of(m))
                n += 1
            else:
                bad.append((res.custom_id, res.result.type))
        b["collected"] = True
        print(b["id"], f"{n}쪽 저장")
    st.setdefault("problems", []).extend(bad)
    save_state(st)
    cost = usage["input"] / 1e6 * 2 + usage["output"] / 1e6 * 10
    print(f"누적 토큰 입력 {usage['input']:,} 출력 {usage['output']:,} → 배치 요금 약 ${cost:.2f} (Opus 5.5 기준)")
    if bad:
        print("문제 쪽:", bad)


def cmd_one(a):
    cl = client()
    doc = pymupdf.open(PDF)
    m = cl.messages.create(**params(doc, a.page, a.model))
    print(m.usage.input_tokens, m.usage.output_tokens, m.stop_reason, file=sys.stderr)
    t = text_of(m)
    if a.save:
        open(os.path.join(OUT, f"p{a.page:04d}.md"), "w", encoding="utf-8").write(t)
    print(t)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("submit"); s.add_argument("--pages", required=True); s.add_argument("--model", default=MODEL)
    s.add_argument("--limit", type=int, default=0); s.add_argument("--per-batch", type=int, default=250)
    sp.add_parser("status"); sp.add_parser("collect")
    o = sp.add_parser("one"); o.add_argument("page", type=int); o.add_argument("--model", default=MODEL)
    o.add_argument("--save", action="store_true")
    a = ap.parse_args()
    {"submit": cmd_submit, "status": cmd_status, "collect": cmd_collect, "one": cmd_one}[a.cmd](a)
