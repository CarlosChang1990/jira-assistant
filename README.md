# 🤖 Jira Assistant Bot

> 整合 Mattermost × Jira × Google Gemini 的智慧開票助理  
> PM 只要用**自然語言**對話，機器人就能自動完成 Jira 開票、版本管理與任務分派。

---

## 目錄

- [功能總覽](#-功能總覽)
- [系統架構](#-系統架構)
- [專案結構](#-專案結構)
- [快速開始](#-快速開始)
- [運行模式](#-運行模式)
- [部署](#️-部署)
- [核心功能詳解](#-核心功能詳解)
- [工具腳本](#-工具腳本)
- [環境變數](#-環境變數)
- [業務規則與限制](#️-業務規則與限制)
- [測試](#-測試)
- [技術棧](#-技術棧)

---

## ✨ 功能總覽

| 功能 | 說明 |
|------|------|
| **智慧開票** | 從自然語言自動解析 Feature / Bug / 維運 / 補建 Task 四種票券類型 |
| **自動拆票** | Feature 需求自動拆成 Story + 多張職能 Task（BE / FE / APP / UX） |
| **版本管理** | 根據上版日期與系統，自動計算或建立 Hotfix 版本號 |
| **人員解析** | 支援「給我」、人名模糊比對，自動對應 Jira Account ID |
| **Sprint 分配** | 建票前列出可用 Sprint，支援分別指定或 LLM 智慧分配 |
| **Component 匹配** | BU 業務單位自動辨識，模糊比對 + 候選清單選擇 |
| **多輪對話** | 資訊不足時主動反問，支援跨訊息收集開票資訊 |
| **版本自動發布** | 掃描並發布已到期的 Jira 版本（所有票券已完成的版本） |
| **雲端接管** | 本機開發時可一鍵暫停雲端 Bot，結束後自動恢復 |

---

## 🏛️ 系統架構

```
┌──────────────┐      WebSocket       ┌────────────────────────────────────────────┐
│  Mattermost  │◄────────────────────►│           Jira Assistant Bot              │
│  (Chat)      │                      │                                            │
└──────────────┘                      │  ┌──────────────┐   ┌──────────────────┐  │
                                      │  │ MattermostBot │   │     LocalBot     │  │
                                      │  │  (Production) │   │  (CLI Testing)   │  │
                                      │  └──────┬───────┘   └────────┬─────────┘  │
                                      │         └──────┬─────────────┘            │
                                      │                ▼                           │
                                      │        ┌──────────────┐                   │
                                      │        │ BotLogicMixin│ ◄── 核心流程      │
                                      │        └──────┬───────┘                   │
                                      │     ┌─────────┼────────────┐              │
                                      │     ▼         ▼            ▼              │
                                      │ ┌────────┐ ┌────────┐ ┌──────────────┐   │
                                      │ │  Jira  │ │  LLM   │ │  Component   │   │
                                      │ │Service │ │Service │ │   Matcher    │   │
                                      │ └───┬────┘ └───┬────┘ └──────────────┘   │
                                      └─────┼─────────┼──────────────────────────┘
                                            ▼         ▼
                                      ┌──────────┐ ┌──────────────┐
                                      │ Jira API │ │ Google Gemini│
                                      └──────────┘ └──────────────┘
```

---

## 📁 專案結構

```
jira-assistant/
├── main.py                      # 正式環境入口（含 Health Check Server）
├── local_run.py                 # 本機測試入口（CLI 模式 / 雲端接管模式）
├── config.py                    # 環境變數載入 & 人員對應表索引
│
├── services/                    # 核心服務層
│   ├── bot_logic.py             # 🧠 核心開票流程（BotLogicMixin）
│   ├── jira_service.py          # Jira REST API 封裝
│   ├── llm_service.py           # LLM 提示工程（Google Gemini）
│   ├── mattermost.py            # Mattermost WebSocket Bot
│   └── component_matcher.py     # BU Component 模糊比對引擎
│
├── models/
│   └── ticket.py                # Pydantic 資料模型（TicketDraft / TicketPlan）
│
├── utils/                       # 工具腳本
│   ├── sync_users.py            # 從 Jira 同步使用者至 users.json
│   ├── build_email_mapping.py   # Email 對應表建構
│   ├── import_jira_excel.py     # 從 Excel 匯入 Jira 人員資料
│   ├── import_mm_names.py       # 匯入 Mattermost 使用者名稱
│   ├── inspect_components.py    # 檢視 Jira Components
│   ├── inspect_versions.py      # 檢視 Jira Versions
│   ├── list_models.py           # 列出可用的 LLM 模型
│   └── test_org_api.py          # 測試 Jira Organization API
│
├── tests/                       # 單元測試 & 重現測試
│
├── release_versions.py          # 自動發布到期版本工具
├── users.json                   # 使用者暱稱 ↔ Jira Account ID 對應表
├── jira_user_list.xlsx          # Jira 使用者匯出原始資料
│
├── deploy_cloud_run.sh          # 部署腳本（Google Cloud Run）
├── deploy_vm.sh                 # 部署腳本（Google Compute Engine VM）
├── Dockerfile                   # Docker 映像檔定義
├── requirements.txt             # Python 依賴套件
├── .env.example                 # 環境變數範本
└── .gitignore
```

---

## 🚀 快速開始

### 1. 安裝依賴

```bash
# 建議使用虛擬環境
python3 -m venv .venv
source .venv/bin/activate

# 安裝套件
pip install -r requirements.txt
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入 Jira / Mattermost / Google API 連線資訊
```

### 3. 設定人員對應 (`users.json`)

`users.json` 儲存 Jira Account ID 與暱稱的對應關係，用於將自然語言中的人名解析為 Jira 帳號：

```json
{
    "6333b81a2eaaa5dcfa14d33c": ["CarlosChang", "k2447", "yungjui.chang"],
    "6331072d234d44d406d18e49": ["jenny", "Jenny", "jenny.wu"]
}
```

> 💡 可使用 `python3 utils/sync_users.py` 自動同步 Jira 使用者，無需手動維護。

### 4. 啟動

```bash
# 本機 CLI 測試（推薦入門）
python3 local_run.py
```

---

## 🎮 運行模式

| 模式 | 指令 | 說明 |
|------|------|------|
| **CLI 測試** | `python3 local_run.py` | 命令列互動測試，不連線 Mattermost |
| **CLI + Dry Run** | `python3 local_run.py --dry-run` | 模擬開票，不真的建立 Jira 票券 |
| **CLI + Debug** | `python3 local_run.py --debug` | 啟用 DEBUG 等級日誌 |
| **接管模式** | `python3 local_run.py --real` | 連線 Mattermost Bot，自動停用雲端服務 |
| **接管 + Dry Run** | `python3 local_run.py --real --dry-run` | 連線 Mattermost 但不真的建票 |
| **恢復雲端** | `python3 local_run.py --restore` | 重新啟用 Cloud Run Bot & GCE VM |
| **正式部署** | `python3 main.py` | 用於雲端（含 Health Check Server） |

### 本機接管機制

使用 `--real` 模式時，系統會自動：

1. **停用 Cloud Run** — 將 `BOT_ENABLED` 設為 `false`（Bot 停止監聽，但保持 Health Check）
2. **停用 GCE VM** — 停止 VM 避免重複處理
3. **啟動本機 Bot** — 以 WebSocket 連線 Mattermost，訊息前方加上 🏠 `[LOCAL]` 標記
4. **手動恢復** — 使用 `--restore` 或結束程式後手動恢復

> ⚠️ 需在 `.env` 中設定 `CLOUD_RUN_SERVICE_NAME`、`CLOUD_RUN_REGION` 及 `GCP_PROJECT_ID`。

---

## ☁️ 部署

### Google Cloud Run

```bash
./deploy_cloud_run.sh
```

腳本會自動讀取 `.env`，建構容器映像並部署至 Cloud Run。關鍵參數：

| 參數 | 值 | 說明 |
|------|------|------|
| `--min-instances` | 1 | 保持至少一個實例（WebSocket 需要常駐） |
| `--max-instances` | 1 | 限制單實例防止重複回覆 |
| `--no-cpu-throttling` | — | 閒置時不限制 CPU（WebSocket 需要） |
| `--timeout` | 3600 | WebSocket 連線最長 1 小時 |

### Google Compute Engine (VM)

```bash
./deploy_vm.sh
```

適合需要長時間 WebSocket 連線的場景。使用 Container-Optimized OS (COS) + Docker。

---

## 📖 核心功能詳解

### 1. 智慧票券類型辨識

機器人透過**兩層關鍵字系統**自動辨識票券類型：

| 層級 | 說明 | 範例關鍵字 |
|------|------|-----------|
| **L1 宣告型** | 使用者明確指定類型 | 「功能票」「bug」「維運票」 |
| **L2 描述型** | 從內容推論 | 「錯誤」「壞掉」「異常」「修復」 |

- L1 優先於 L2
- 若 L1 多種類型衝突，會列出選項讓使用者選擇

#### 支援的票券類型

| 類型 | Jira Issue Type | 結構 |
|------|----------------|------|
| **Feature** | Story + Feature Task | Story（業務需求）+ 多張 Task（職能分工） |
| **Bug** | Bug | 單張 Bug 票 |
| **Operational** | Operational Task | 單張維運票（自動指派 Active Sprint） |
| **Add Task** | Feature Task | 為既有 Story 補建子 Task |

### 2. 自動拆票策略

**Feature 票**的拆票邏輯：

```
使用者：「短租要開發新功能，排車表新增欄位，後端 John，前端 Allen 和 Grey」

機器人自動建立：
  ├── 📋 Story:  [SR] 排車表新增欄位          → Components: [短租(SR)]
  ├── 🔨 Task:   [SR-BE] 排車表新增欄位       → Components: [短租(SR), BE] → Assignee: John
  ├── 🔨 Task:   [SR-FE] 排車表新增欄位       → Components: [短租(SR), FE] → Assignee: Allen
  └── 🔨 Task:   [SR-FE] 排車表新增欄位       → Components: [短租(SR), FE] → Assignee: Grey
```

- Story 的 Assignee 預設為對話者（`me`）
- Task 之間透過 **Blocks** 連結至 Story

### 3. 版本管理 (Hotfix Automation)

當使用者指定上版日期與系統前綴時，機器人會自動：

1. **搜尋同日版本** → 直接使用
2. **找前一版本** → 版號尾數 +1，加上日期後綴
3. **範例**：前一版 `WP2.100.6(260303)` → 新版 `WP2.100.7(260305)`
4. **Hotfix Label**：若版本 Patch 號 ≠ 0，自動標記 `Hotfix` Label

### 4. 人員解析（Solution E）

```
使用者輸入 → 暱稱匹配（users.json）→ Jira Account ID
```

匹配優先順序：

| 優先 | 匹配方式 | 說明 |
|------|---------|------|
| 1 | 精確匹配 | `"John"` → 唯一對應的 Account ID |
| 2 | 模糊匹配 | Substring 比對（query ⊆ nickname or nickname ⊆ query） |
| 3 | Jira API 搜尋 | 以 email 或名稱搜尋 Jira |
| — | 多重匹配 | 列出候選清單，讓使用者選擇 |

特殊規則：
- `「給我」` `「我自己」` → 自動解析為對話者的 Jira 帳號
- Mattermost Bot 額外支援：username → email prefix → Jira API fallback

### 5. BU Component 匹配

`ComponentMatcher` 從 Jira 快取 BU Components，並提取比對 Token：

```
Jira Component: "短租(SR)"
→ Tokens: ["短租", "sr"]
→ 使用者說「短租」或「SR」皆可匹配
```

比對層次：
1. **Tier 1** — 完整名稱精確匹配
2. **Tier 2** — Token 比對（英文強制 Word Boundary，中文 Substring）
3. **未匹配** — 列出所有 BU 選項

### 6. Sprint 分配

- **Feature / Bug** — 列出 Active + Future Sprint 供選擇
- **Operational** — 自動指派 Active Sprint
- 支援 LLM 解析複雜分配指令（如：「Story 放 129，Task 放 130」）

### 7. 主動反問與澄清

| 缺失資訊 | 機器人行為 |
|----------|-----------|
| 票券類型不明 | 詢問：功能 / Bug / 維運？ |
| BU 不明確 | 列出業務單位選項 |
| Task 拆分不明 | 詢問：需要哪些職能？ |
| 負責人不明 | 詢問：誰負責？ |
| 上版日期不明 | 詢問（支援「不急」免填） |
| 系統前綴不明 | 詢問或列出選項 |
| Component 不存在 | 模糊比對，列出相似項目供選擇 |

---

## 🔧 工具腳本

### 使用者同步

```bash
# 從 Jira 自動同步所有使用者至 users.json
python3 utils/sync_users.py
```

### 版本自動發布

```bash
# Dry Run（只看不做）
python3 release_versions.py --dry-run

# 正式發布
python3 release_versions.py
```

邏輯：掃描所有「未發布 + 已到期」的版本 → 若所有票券已完成則標記為已發布 → 若有未完成票券則跳過。

### 偵錯工具

```bash
python3 debug_issue_types.py        # 列出專案可用的 Issue Types
python3 utils/inspect_components.py # 檢視 Jira Components
python3 utils/inspect_versions.py   # 檢視 Jira Versions
python3 utils/list_models.py        # 列出可用的 Gemini 模型
```

---

## 📝 環境變數

| 變數 | 必填 | 說明 |
|------|:----:|------|
| `JIRA_SERVER` | ✅ | Jira 伺服器 URL |
| `JIRA_EMAIL` | ✅ | Jira 登入 Email |
| `JIRA_API_TOKEN` | ✅ | Jira API Token |
| `JIRA_PROJECT_KEY` | ✅ | 預設 Jira 專案 Key（如 `KAN`） |
| `JIRA_BOARD_ID` | ✅ | Sprint 所屬 Board ID |
| `GOOGLE_API_KEY` | ✅ | Google Gemini API Key |
| `MATTERMOST_URL` | ✅ | Mattermost 伺服器 URL（不含 `https://`） |
| `MATTERMOST_TOKEN` | ✅ | Mattermost Bot Access Token |
| `MATTERMOST_SCHEME` | — | `https` 或 `http`（預設 `https`） |
| `MATTERMOST_PORT` | — | 連接埠（預設 `443`） |
| `MATTERMOST_TEAM` | — | Mattermost Team 名稱 |
| `GCP_PROJECT_ID` | — | GCP 專案 ID（部署 & 接管用） |
| `CLOUD_RUN_SERVICE_NAME` | — | Cloud Run 服務名稱（接管用） |
| `CLOUD_RUN_REGION` | — | Cloud Run 區域（接管用） |

---

## ⚠️ 業務規則與限制

1. **例行發版先行** — Hotfix 版本計算依賴已存在的例行版本，版號為 `前一版 Patch + 1`
2. **前一版本必須存在** — 若目標日期前無任何版本，將建立初始版 `1.0.0(YYMMDD)`
3. **系統前綴取自 Unreleased 版本** — 只列出尚未發布版本的系統前綴
4. **DM Only** — Mattermost Bot 僅回應 1-on-1 私訊，忽略群組頻道
5. **定期同步 users.json** — 新成員加入團隊後需執行 `sync_users.py`
6. **對話狀態獨立** — 每個 Channel / Session 獨立維護對話歷史（最多保留 30 則）

---

## 🧪 測試

```bash
# 執行所有測試
python3 -m pytest tests/

# 執行特定測試
python3 -m pytest tests/test_bot_flow.py -v
```

測試涵蓋：

| 類別 | 檔案 | 說明 |
|------|------|------|
| 開票流程 | `test_bot_flow.py`, `test_bot_full.py` | 端到端開票流程測試 |
| 澄清問答 | `test_clarification.py`, `test_assignee_question.py` | 反問邏輯測試 |
| 人員匹配 | `test_user_mapping.py`, `test_user_mapping_logic.py`, `test_user_search.py` | 暱稱解析測試 |
| 版本管理 | `test_hotfix.py`, `test_hotfix_label.py`, `test_release_date.py` | Hotfix 版本計算測試 |
| 票券解析 | `test_breakdown.py`, `test_create_ticket.py`, `test_context.py` | 拆票與解析測試 |
| 偵錯重現 | `repro_*.py`, `debug_regex.py` | Bug 重現與 Regex 偵錯 |

---

## 🛠️ 技術棧

| 類別 | 技術 |
|------|------|
| **Language** | Python 3.10+ |
| **LLM** | Google Gemini 2.5 Flash（via LangChain） |
| **Chat** | Mattermost（via `mattermostautodriver` WebSocket） |
| **Issue Tracker** | Jira Cloud（via `jira` Python SDK） |
| **Data Model** | Pydantic v2 |
| **Deployment** | Docker → Google Cloud Run / GCE VM |
| **CI/CD** | `gcloud` CLI |

---

## 📄 License

Private — Internal use only.
