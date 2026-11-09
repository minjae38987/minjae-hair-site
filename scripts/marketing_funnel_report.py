#!/usr/bin/env python3
"""Aggregate-only marketing report. No personal information or external API calls."""
import argparse
import csv
from datetime import datetime
from pathlib import Path

FIELDS = ("date", "channel", "impressions", "content_clicks", "booking_clicks",
          "confirmed_bookings", "paid_new_customers", "spend_krw")
COUNTS = FIELDS[2:]

def load_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or tuple(reader.fieldnames) != FIELDS:
            raise ValueError("CSV columns must be: " + ",".join(FIELDS))
        rows = []
        for lineno, row in enumerate(reader, 2):
            try:
                datetime.strptime(row["date"], "%Y-%m-%d")
                channel = row["channel"].strip()
                if not channel:
                    raise ValueError("channel is empty")
                values = {k: int(row[k]) for k in COUNTS}
                if any(v < 0 for v in values.values()):
                    raise ValueError("negative count")
                rows.append({"date": row["date"], "channel": channel, **values})
            except (ValueError, TypeError) as exc:
                raise ValueError(f"row {lineno}: {exc}") from exc
    return rows

def report(rows, target=100):
    if type(target) is not int or target < 1:
        raise ValueError("target must be positive")
    groups = {}
    for row in rows:
        totals = groups.setdefault(row["channel"], {k: 0 for k in COUNTS})
        for key in COUNTS:
            totals[key] += row[key]
    total = {key: sum(group[key] for group in groups.values()) for key in COUNTS}
    has_data = bool(rows)
    def ratio(numerator, denominator):
        return f"{numerator / denominator * 100:.1f}%" if denominator else "N/A"
    lines = [
        "# 민재 신규 고객 마케팅 집계",
        "",
        "> 집계 기준: 직접 입력한 채널별 합계. 채널 간 중복 이용자를 제거하지 않으며, GA4 예약 클릭을 실제 예약으로 간주하지 않습니다.",
        "",
        "| 채널 | 노출 | 콘텐츠 클릭 | 예약 링크 클릭 | 확정 예약 | 유료 신규 방문 | 비용(원) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for channel, values in sorted(groups.items()):
        lines.append("| " + channel.replace("|", "/") + " | " +
                     " | ".join(str(values[key]) for key in COUNTS) + " |")
    if has_data:
        lines.append("| **합계** | " + " | ".join(str(total[key]) for key in COUNTS) + " |")
    else:
        lines.append("| 미측정 | - | - | - | - | - | - |")
    lines.extend([
        "",
        f"- 목표 대비 유료 신규 방문: **{str(total['paid_new_customers']) + '/' + str(target) + '명' if has_data else '미측정 (입력된 실적 없음)'}**",
        f"- 달성률(집계된 수 기준): **{ratio(total['paid_new_customers'], target) if has_data else '미측정'}**",
        f"- 콘텐츠 클릭/노출(이벤트 비율): {ratio(total['content_clicks'], total['impressions'])}",
        f"- 예약 클릭/콘텐츠 클릭(이벤트 비율): {ratio(total['booking_clicks'], total['content_clicks'])}",
        f"- 확정 예약/예약 클릭(이벤트 비율): {ratio(total['confirmed_bookings'], total['booking_clicks'])}",
        f"- 총 비용: {total['spend_krw']:,}원",
        "",
        "## 해석 시 주의",
        "- 노출 및 클릭은 횟수일 수 있으며, 사람 수 또는 고유 세션 전환율이 아닙니다.",
        "- 네이버 예약 및 매장 매출 자료로 확정 예약과 유료 신규 방문을 별도 검증하세요.",
        "- 고객 이름·전화번호·예약번호 등 개인정보는 이 CSV에 입력하지 마세요.",
        "- 같은 유료 고객을 둘 이상의 채널에 중복 집계하지 마세요. 출처가 불명확하면 'unknown'으로 기록하세요.",
        "- 0건 또는 수집 불가 데이터를 구분하려면 운영 시 수집 불가 내역을 별도로 기록하세요. 0은 미측정을 의미하지 않습니다.",
        "",
    ])
    return "\n".join(lines)

def main():
    p = argparse.ArgumentParser(description="Create aggregate-only channel report")
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="output/marketing-funnel-report.md")
    p.add_argument("--target", type=int, default=100)
    args = p.parse_args()
    rows = load_rows(args.input)
    result = report(rows, args.target)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(result, encoding="utf-8")
    print(f"REPORT_WRITTEN {dest}")

if __name__ == "__main__":
    main()
