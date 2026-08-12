# 全球市場與 AI 瓶頸報告自動化

這個儲存庫使用 GitHub Actions 在雲端生成：

- 週一至週五 08:00 前：早報＋AI瓶頸潛力股雷達
- 週一至週五 20:00 前：晚報＋AI瓶頸潛力股雷達
- 星期六 12:00 前：完整週報＋完整雷達
- 星期日 09:00：重大事件檢查，未達門檻不產報

電腦可以關機。工作由 GitHub 的雲端執行器完成。

## 實際啟動時間

GitHub Actions 排程採 `Asia/Taipei`：

| 內容 | 啟動時間 | 目標完成時間 |
|---|---:|---:|
| 平日早報 | 週一至週五 07:15 | 08:00 前 |
| 平日晚報 | 週一至週五 19:15 | 20:00 前 |
| 完整週報 | 星期六 11:00 | 12:00 前 |
| 重大事件檢查 | 星期日 08:30 | 09:00 前 |

排程可能因 GitHub Actions 負載而稍有延遲；每份報告都會顯示實際截止時間。

公開儲存庫若連續60天沒有活動，GitHub可能自動停用排程；屆時到 `Actions` 頁重新啟用即可。手動執行與報告commit本身也會形成活動紀錄。

## 0→1 啟用步驟

### 1. 安裝與登入 GitHub CLI（Windows）

```powershell
winget install --id GitHub.cli
gh auth login
gh auth status
```

### 2. 進入本機儲存庫

```powershell
cd C:\Users\d93ja\Documents\Codex\teasale
```

### 3. 設定 Git 作者資料

```powershell
git config user.name "你的GitHub名稱"
git config user.email "你的GitHub信箱"
```

### 4. 第一次提交與推送

```powershell
git add .
git commit -m "build: add cloud report automation"
git push -u origin main
```

如果空儲存庫首次推送要求登入，依瀏覽器提示授權即可。

### 5. 建立 OpenAI API 金鑰

到 [OpenAI API Keys](https://platform.openai.com/api-keys) 建立金鑰。API使用量與ChatGPT訂閱分開計費。

### 6. 把金鑰放入 GitHub Secret

進入儲存庫：`Settings` → `Secrets and variables` → `Actions` → `New repository secret`。

- Name：`OPENAI_API_KEY`
- Secret：貼上API金鑰

不要把金鑰放進 `main.yml`、Python檔或任何commit。

### 7. 第一次乾跑測試

進入 `Actions` → `AI Market Reports` → `Run workflow`：

- edition：`morning`
- dry_run：勾選 `true`

乾跑不呼叫OpenAI API，只測試依賴、中文PDF、檔案輸出與Artifact。

### 8. 第一次真實測試

再次選擇 `Run workflow`：

- edition：`morning`
- dry_run：`false`

完成後可在該次工作底部下載Artifact；正式報告也會提交到 `reports/YYYY-MM-DD/`。

若主分支保護規則禁止機器人直接提交，Artifact仍會保留；可再把工作流程改成自動建立Pull Request。

## 可選設定

在 `Settings` → `Secrets and variables` → `Actions` → `Variables` 可新增：

- `OPENAI_MODEL`：預設 `gpt-5.6-terra`
- `OPENAI_REASONING_EFFORT`：預設 `medium`

## 本機測試

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python src/generate_report.py --edition morning --dry-run --output-root .smoke
```

## 輸出

- `reports/YYYY-MM-DD/*.md`
- `reports/YYYY-MM-DD/*.html`
- `reports/YYYY-MM-DD/*.pdf`
- `history/runs.csv`

報告程式使用OpenAI Responses API與Web Search搜尋最新資料，再依 `prompts/report_prompt.md` 的固定規則生成。正式交易前仍需以交易所、公司公告與券商即時報價再次核驗。
