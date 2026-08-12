"""빌드된 주간 신문 PDF를 사이트 저장소에 배치하고 목록(issues/index.json)을 갱신한다.

워크플로(build-issue.yml)가 `builder/dist/<월요일>/`에 PDF와 report.json을 만든 뒤 호출한다.
사이트(index.html)는 issues/index.json만 읽어 '이번 호 PDF' 목록을 그린다.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]      # 사이트 저장소 루트
MONDAY = os.environ["MONDAY"]
# BUILDER_DIST는 로컬 검증용 오버라이드 — CI에서는 체크아웃된 builder/dist를 쓴다.
SRC = Path(os.environ.get("BUILDER_DIST") or (ROOT / "builder" / "dist")) / MONDAY
DEST = ROOT / "issues" / MONDAY
INDEX = ROOT / "issues" / "index.json"

MEDIA_ORDER = ["Kinder", "Kids", "Junior", "Times"]

# PDF 1주분이 약 4MB라 무한정 쌓으면 저장소가 커진다 — 최근 N주만 남기고 지운다.
KEEP_WEEKS = 8


def main() -> int:
    if not SRC.is_dir():
        print(f"✗ 산출물 폴더가 없습니다: {SRC}")
        return 1

    # 신문 PDF만 — 표지 안 비교용(Cover_Compare_*.pdf)은 사이트에 올리지 않는다.
    # 접두사로 거르지 않는 이유: 제호가 바뀌면(JP_Times_ → TopNews_) 조용히 0건이 된다.
    pdfs = [f for f in sorted(SRC.glob("*.pdf")) if not f.name.startswith("Cover_Compare")]
    if not pdfs:
        print(f"✗ PDF가 없습니다: {SRC}")
        return 1

    DEST.mkdir(parents=True, exist_ok=True)
    for stale in DEST.glob("*.pdf"):        # 제호 변경 등으로 파일명이 바뀌면 옛 PDF가 남는다
        stale.unlink()
    report = {}
    report_path = SRC / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        shutil.copy2(report_path, DEST / "report.json")

    # PDF 이름 → 매체 요약 매핑 (report.json의 output에서 면수·수량을 가져온다)
    by_short = {}
    for out in report.get("output", []):
        pdf = out.get("pdf") or ""
        if pdf:
            by_short[Path(pdf).name] = out

    files = []
    for pdf in pdfs:
        shutil.copy2(pdf, DEST / pdf.name)
        info = by_short.get(pdf.name, {})
        files.append({
            "file": f"issues/{MONDAY}/{pdf.name}",
            "name": pdf.name,
            "media": info.get("title", pdf.stem),
            "level": info.get("level", ""),
            "pages": info.get("pages", 0),
            "articles": len(info.get("selected", [])) or max(0, info.get("pages", 2) - 2),
            "quota": info.get("quota"),
            "found": info.get("found"),
            "quota_status": info.get("quota_status", ""),
            "size_kb": round((DEST / pdf.name).stat().st_size / 1024),
        })

    def order(entry: dict) -> int:
        for i, short in enumerate(MEDIA_ORDER):
            if short.lower() in entry["name"].lower():
                return i
        return len(MEDIA_ORDER)

    files.sort(key=order)

    issues = []
    if INDEX.exists():
        try:
            issues = json.loads(INDEX.read_text(encoding="utf-8")).get("issues", [])
        except json.JSONDecodeError:
            issues = []
    issues = [i for i in issues if i.get("week") != MONDAY]      # 같은 주는 새 결과로 교체
    issues.append({
        "week": MONDAY,
        "week_range": report.get("week_range", [MONDAY, MONDAY]),
        "generated_at": report.get("generated_at", ""),
        "format": report.get("format", {}),
        "files": files,
    })
    issues.sort(key=lambda i: i["week"], reverse=True)           # 최신 호가 위로

    dropped = issues[KEEP_WEEKS:]                                # 오래된 호는 파일까지 정리
    issues = issues[:KEEP_WEEKS]
    for old in dropped:
        folder = ROOT / "issues" / old["week"]
        if folder.is_dir():
            shutil.rmtree(folder)
            print(f"· 오래된 호 삭제: {old['week']}")

    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps({"issues": issues}, ensure_ascii=False, indent=2),
                     encoding="utf-8")

    print(f"✓ {MONDAY} PDF {len(files)}종 배치 → issues/{MONDAY}/")
    for f in files:
        print(f"   {f['media']:<18} {f['pages']:>2}면  {f['size_kb']:>5}KB  {f['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
