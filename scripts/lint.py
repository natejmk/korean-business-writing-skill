#!/usr/bin/env python3
"""business-writing 검사기. 표준 라이브러리만 사용한다.

사용: python3 lint.py 파일.md|파일.txt|파일.docx [--review]
종료 코드: 0 통과, 1 error 있음, 2 사용 오류
검사 제외: 줄 끝에 <!-- lint-exempt --> 를 달거나 줄에 (X) 표기가 있으면 건너뛴다.
"""
import argparse
import pathlib
import re
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SUBST = ROOT / "references" / "substitutions.md"
EXEMPT = ("(X)", "lint-exempt")
BUFFERS = ["가능성이 있", "여지가 있", "측면이 있", "경향이 있", "수도 있", "일정 부분",
           "어느 정도", "대체로", "편이다", "듯하", "것으로 판단", "것으로 보인", "추정된다"]
CONNECT = re.compile(r"[가-힣]고(?=\s)|[가-힣]며(?=[\s,])")
ENDINGS = [("합니다체", re.compile(r"(니다|십시오)$")), ("해요체", re.compile(r"요$")),
           ("명사형", re.compile(r"[함임됨음]$")), ("평서체", re.compile(r"다$"))]


def load_rules():
    rules = []
    if not SUBST.exists():
        return rules
    for raw in SUBST.read_text(encoding="utf-8").splitlines():
        cells = [c.strip().strip("`") for c in raw.strip().strip("|").split("|")]
        if raw.startswith("|") and len(cells) == 3 and cells[2] in ("error", "review"):
            rules.append((cells[0], cells[1], cells[2]))
    return rules


def read_units(path):
    """(줄 번호, 본문, 제목 여부) 목록을 돌려준다. 코드 블록과 인라인 코드는 제외한다."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
        texts = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in paras]
        return [(i, t, False) for i, t in enumerate(texts, 1) if t.strip()]
    units, fenced = [], False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or any(m in line for m in EXEMPT) or re.match(r"^\s*\|?[\s:|-]+\|?\s*$", line):
            continue
        body = re.sub(r"`[^`]*`", "", line)
        units.append((i, body, body.lstrip().startswith("#")))
    return units


def sentences(text):
    text = re.sub(r"^\s*([-*]|\d+\.)\s+", "", text)
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def classify(sentence):
    tail = sentence.rstrip(".!?:) ")
    for name, pattern in ENDINGS:
        if pattern.search(tail):
            return name
    return None


def check(path, show_review):
    rules = load_rules()
    units = read_units(path)
    findings, ends = [], {}
    is_md = path.suffix.lower() != ".docx"
    for no, text, heading in units:
        for ch in ("·", "ㆍ"):
            if ch in text:
                findings.append((no, "error", "11", f"가운데점 사용 '{ch}'", "쉼표 또는 '와/과'"))
        for bad, good, tier in rules:
            if bad in text and (tier == "error" or show_review):
                findings.append((no, tier, "12/20/21/22", f"'{bad}'", good))
        if heading:
            title = text.lstrip("# ").strip()
            if re.search(r"([한했된있없이]다|니다|[해세에]요|까\?)\.?$", title):
                findings.append((no, "warn", "19", f"서술형 제목 '{title}'", "명사구로 변경"))
            continue
        if text.lstrip().startswith("|"):
            continue
        for s in sentences(text):
            hits = [b for b in BUFFERS if b in s]
            if len(hits) >= 2:
                findings.append((no, "warn", "23", f"완충어 중복 {hits}", "하나만 남김"))
            if len(CONNECT.findall(s)) >= 3:
                findings.append((no, "warn", "13", "연결어미 3회 이상 나열", "문장을 나눔"))
            kind = classify(s)
            if kind:
                ends.setdefault(kind, []).append(no)
    total = sum(len(v) for v in ends.values())
    if total >= 8 and len(ends) > 1:
        major = max(ends, key=lambda k: len(ends[k]))
        for kind, lines in ends.items():
            if kind != major and len(lines) >= 3 and len(lines) / total >= 0.15:
                findings.append((lines[0], "warn", "6",
                                 f"종결어미 혼용: {major} {len(ends[major])}건, {kind} {len(lines)}건",
                                 f"주 종결 {major}에 맞춤 ({kind} 줄 {lines[:5]})"))
    if is_md:
        findings += numbering(units)
    return sorted(findings)


def numbering(units):
    out, expect_h1, expect_h2 = [], None, {}
    for no, text, heading in units:
        if not heading:
            continue
        m = re.match(r"^#+\s*(\d+)\.(\d+)?\s", text)
        if not m:
            continue
        major, minor = int(m.group(1)), m.group(2)
        if minor is None:
            if expect_h1 is not None and major != expect_h1:
                out.append((no, "warn", "31", f"번호 불연속: {expect_h1}번이어야 하나 {major}번", "번호 재정렬"))
            expect_h1 = major + 1
        else:
            want = expect_h2.get(major, 1)
            if int(minor) != want:
                out.append((no, "warn", "31", f"번호 불연속: {major}.{want}이어야 하나 {major}.{minor}", "번호 재정렬"))
            expect_h2[major] = int(minor) + 1
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--review", action="store_true", help="판단이 필요한 review 등급도 보고")
    args = ap.parse_args()
    failed = False
    for name in args.files:
        path = pathlib.Path(name)
        if not path.exists():
            print(f"{name}: 파일이 없다", file=sys.stderr)
            return 2
        results = check(path, args.review)
        for no, tier, rule, msg, fix in results:
            print(f"{path}:{no}: [{tier}] 규칙 {rule} {msg} -> {fix}")
        errors = sum(1 for r in results if r[1] == "error")
        print(f"{path}: error {errors}건, 그 밖 {len(results) - errors}건")
        failed = failed or errors > 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
