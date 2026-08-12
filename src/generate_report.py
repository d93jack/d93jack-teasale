from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")
UNIVERSE_PATH = ROOT / "config" / "universe.json"
PROMPT_PATH = ROOT / "prompts" / "report_prompt.md"

EDITION_LABELS = {
    "morning": ("早報", "台股開盤前"),
    "evening": ("晚報", "台股與亞洲盤後／美股開盤前"),
    "weekly": ("週末完整重評", "本週回顧與下週布局"),
    "sunday-check": ("星期日重大事件特別報告", "僅重大事件才產出"),
}


@dataclass(frozen=True)
class GeneratedReport:
    generated: bool
    edition: str
    date: str
    output_files: list[str]
    reason: str


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_citations(response: Any) -> list[dict[str, str]]:
    payload = response.model_dump() if hasattr(response, "model_dump") else response
    found: dict[str, str] = {}
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            for annotation in content.get("annotations", []):
                if annotation.get("type") != "url_citation":
                    continue
                url = annotation.get("url") or annotation.get("url_citation", {}).get("url")
                title = annotation.get("title") or annotation.get("url_citation", {}).get("title") or url
                if url:
                    found[url] = title
    return [{"title": title, "url": url} for url, title in found.items()]


def append_sources(markdown_text: str, citations: list[dict[str, str]]) -> str:
    if not citations:
        return markdown_text.rstrip() + "\n"
    lines = [markdown_text.rstrip(), "", "## API搜尋來源", ""]
    for citation in citations:
        title = citation["title"].replace("[", "").replace("]", "")
        lines.append(f"- [{title}]({citation['url']})")
    return "\n".join(lines) + "\n"


def report_prompt(edition: str, now: datetime, universe: dict[str, Any], base_spec: str) -> str:
    label, purpose = EDITION_LABELS[edition]
    exposure_lines = [
        f"- {item['symbol']}｜{item['name']}｜{item['market']}｜{item['segment']}"
        for item in universe["formal_exposures"]
    ]
    if len(exposure_lines) != 40:
        raise ValueError(f"正式曝險單位必須是40，目前為{len(exposure_lines)}")
    special = ""
    if edition == "weekly":
        special = "本版必須執行40個曝險單位完整重評與完整雷達。"
    elif edition == "sunday-check":
        special = "這是重大事件特別報告；必須說明事件、傳導路徑、受影響標的、立即風控與下一驗證時間。"
    else:
        special = "本版是每日報告；全部正式池掃描，但只有新證據標的展開深度分析。"
    return f"""{base_spec}

## 本次執行參數

- 版別：{label}
- 用途：{purpose}
- 嚴格資料截止：{now:%Y-%m-%d %H:%M:%S} Asia/Taipei
- 生成時刻：{now.isoformat()}
- {special}

## 40個正式曝險單位

{chr(10).join(exposure_lines)}

## 研究池（最多20）

{', '.join(universe['research_pool'])}

## 供應鏈哨兵

{', '.join(universe['supply_chain_sentinels'])}

請直接輸出完整Markdown主報告。標題、表格、分數、日期、來源URL、資金金額與風險條件不可省略。任何無法在截止前核驗的資料明確寫「待核」。
"""


def radar_prompt(main_report: str, edition: str, now: datetime) -> str:
    label = EDITION_LABELS[edition][0]
    return f"""根據下方已完成的主報告，生成《AI瓶頸潛力股雷達｜{label}》Markdown。

資料截止固定為 {now:%Y-%m-%d %H:%M:%S} Asia/Taipei，不得加入主報告以外的新數據。
只列3–5項真正重要的新變化；沒有重大變化就明確寫出，不可湊數推薦。每項必須包含：新證據、瓶頸傳導、受影響標的、短中長行動、布局/不追/失效條件、下一驗證日期。最後列風險與來源。

--- 主報告開始 ---
{main_report}
--- 主報告結束 ---
"""


def major_event_prompt(now: datetime) -> str:
    return f"""搜尋並判斷截至 {now:%Y-%m-%d %H:%M:%S} Asia/Taipei，星期日是否發生足以在下一交易日前改變全球、美股、台股或AI供應鏈風險狀態的重大事件。

門檻包括：戰爭/制裁顯著升級、央行或政府緊急政策、系統性金融事件、主要交易所/大型AI公司重大意外、關鍵供應鏈中斷、可能造成指數或核心標的大幅跳空的事件。

第一行只能是 `MAJOR_EVENT: YES` 或 `MAJOR_EVENT: NO`。之後用繁體中文列出證據、來源URL與判斷理由。一般評論、重複新聞或小幅價格變動不得算重大事件。
"""


def call_openai(prompt: str, *, use_web: bool) -> tuple[str, list[dict[str, str]], str]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("缺少OPENAI_API_KEY；請在GitHub Secrets設定。")
    from openai import OpenAI

    client = OpenAI()
    kwargs: dict[str, Any] = {
        "model": os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
        "input": prompt,
        "reasoning": {"effort": os.getenv("OPENAI_REASONING_EFFORT", "medium")},
        "store": False,
    }
    if use_web:
        kwargs["tools"] = [{"type": "web_search"}]
    response = client.responses.create(**kwargs)
    return response.output_text, extract_citations(response), response.id


def render_markdown(markdown_text: str, title: str, md_path: Path) -> list[Path]:
    from markdown import markdown
    from weasyprint import HTML

    md_path.write_text(markdown_text, encoding="utf-8")
    html_body = markdown(markdown_text, extensions=["tables", "fenced_code", "sane_lists"])
    css = """
    @page { size: A4; margin: 16mm 14mm 16mm; @bottom-right { content: counter(page); color: #65717f; font-size: 8pt; } }
    body { font-family: 'Noto Sans CJK TC', 'Microsoft JhengHei', sans-serif; color: #172235; font-size: 9.2pt; line-height: 1.48; }
    h1 { color: #0d3159; font-size: 23pt; border-bottom: 3px solid #1597a3; padding-bottom: 7px; }
    h2 { color: #155f99; font-size: 15pt; margin-top: 18px; }
    h3 { color: #147c86; font-size: 11.5pt; }
    table { width: 100%; border-collapse: collapse; margin: 8px 0 14px; font-size: 7.7pt; }
    th { background: #0d3159; color: white; padding: 5px; text-align: left; }
    td { border: 1px solid #ccd5df; padding: 4px; vertical-align: top; }
    tr:nth-child(even) td { background: #f4f7fa; }
    blockquote { border-left: 4px solid #1597a3; background: #eaf7f6; margin: 10px 0; padding: 8px 12px; }
    a { color: #1769aa; text-decoration: none; overflow-wrap: anywhere; }
    code { font-family: monospace; font-size: 8pt; }
    """
    html_text = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{title}</title><style>{css}</style></head><body>{html_body}</body></html>"""
    html_path = md_path.with_suffix(".html")
    pdf_path = md_path.with_suffix(".pdf")
    html_path.write_text(html_text, encoding="utf-8")
    HTML(string=html_text, base_url=str(ROOT)).write_pdf(str(pdf_path))
    return [md_path, html_path, pdf_path]


def dry_run_text(edition: str, now: datetime) -> str:
    label = EDITION_LABELS[edition][0]
    return f"""# 全球市場與 AI 瓶頸{label}｜乾跑測試

> 資料截止：{now:%Y-%m-%d %H:%M:%S} Asia/Taipei

## 執行結果

這是 `--dry-run` 產生的測試內容，不含真實行情或投資判斷。

| 項目 | 狀態 |
|---|---|
| 正式曝險單位 | 40 |
| OpenAI API | 未呼叫 |
| PDF生成 | 測試 |
"""


def write_history(output_root: Path, result: GeneratedReport, now: datetime) -> None:
    history_dir = output_root / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / "runs.csv"
    new_file = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["date", "time_taipei", "edition", "generated", "reason", "output_files"])
        writer.writerow([
            result.date,
            now.strftime("%H:%M:%S"),
            result.edition,
            str(result.generated).lower(),
            result.reason,
            "|".join(result.output_files),
        ])


def generate(edition: str, output_root: Path, dry_run: bool = False) -> GeneratedReport:
    now = datetime.now(TAIPEI)
    universe = load_json(UNIVERSE_PATH)
    if len(universe["formal_exposures"]) != 40:
        raise ValueError("config/universe.json的formal_exposures必須恰好40個。")
    base_spec = PROMPT_PATH.read_text(encoding="utf-8")
    response_ids: list[str] = []

    if edition == "sunday-check" and not dry_run:
        assessment, citations, response_id = call_openai(major_event_prompt(now), use_web=True)
        response_ids.append(response_id)
        assessment = append_sources(assessment, citations)
        if not re.search(r"^MAJOR_EVENT:\s*YES\b", assessment, flags=re.IGNORECASE):
            result = GeneratedReport(False, edition, now.strftime("%Y-%m-%d"), [], "未達重大事件門檻")
            write_history(output_root, result, now)
            (ROOT / "run_result.json").write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
            return result

    if dry_run:
        main_text = dry_run_text(edition, now)
        radar_text = "# AI瓶頸潛力股雷達｜乾跑測試\n\n沒有真實資料；只驗證自動化與檔案輸出。\n"
    else:
        main_text, citations, response_id = call_openai(
            report_prompt(edition, now, universe, base_spec), use_web=True
        )
        response_ids.append(response_id)
        main_text = append_sources(main_text, citations)
        radar_text, _, response_id = call_openai(radar_prompt(main_text, edition, now), use_web=False)
        response_ids.append(response_id)

    date_text = now.strftime("%Y-%m-%d")
    label = EDITION_LABELS[edition][0]
    report_dir = output_root / "reports" / date_text
    report_dir.mkdir(parents=True, exist_ok=True)
    main_stem = f"全球市場與AI瓶頸{label}_{date_text}"
    radar_stem = f"AI瓶頸潛力股雷達_{date_text}_{label}"
    output_paths = render_markdown(main_text, main_stem, report_dir / f"{main_stem}.md")
    output_paths += render_markdown(radar_text, radar_stem, report_dir / f"{radar_stem}.md")
    metadata_path = report_dir / f"metadata_{edition}.json"
    metadata_path.write_text(json.dumps({
        "generated_at": now.isoformat(),
        "edition": edition,
        "model": "dry-run" if dry_run else os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
        "response_ids": response_ids,
        "formal_exposures": 40,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    output_paths.append(metadata_path)
    relative = [str(path.relative_to(output_root)).replace("\\", "/") for path in output_paths]
    result = GeneratedReport(True, edition, date_text, relative, "dry-run" if dry_run else "generated")
    write_history(output_root, result, now)
    (ROOT / "run_result.json").write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate global market and AI bottleneck reports")
    parser.add_argument("--edition", choices=EDITION_LABELS, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generated = generate(args.edition, args.output_root.resolve(), args.dry_run)
    print(json.dumps(generated.__dict__, ensure_ascii=False, indent=2))

