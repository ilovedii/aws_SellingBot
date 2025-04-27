# F5-TTS 在 AWS SageMaker 部署流程說明

本文件說明你在 AWS 上部署 F5-TTS TTS API 的主要步驟與原理。

---

## 1. 建立 SageMaker 執行環境
- 在 AWS 管理台啟動 SageMaker，建立 Notebook Instance 或 Studio，選擇 GPU instance（如 ml.g4dn.xlarge）。
- 指定一個擁有 SageMaker、S3、ECR 權限的 IAM Role，讓服務能存取模型與映像檔。

## 2. 準備 Docker 映像檔
- 使用 F5-TTS 官方 Dockerfile，安裝好 Python、PyTorch、F5-TTS 及其依賴。
- 在 Dockerfile 內加裝 FastAPI 與 Uvicorn，並設定啟動 API 服務（inference.py）。
- 在本地端（或雲端）用 `docker build` 指令建構映像檔。

## inference.py 的作用與放置位置

`inference.py` 是你 API 服務的主程式，負責：
- 接收 HTTP 請求（如 `/tts` 路徑）
- 解析輸入（如 text、ref_audio、ref_text）
- 呼叫 F5-TTS 模型進行推論
- 回傳語音結果

### 放置位置
你必須將 `inference.py` 放在 Docker 映像檔的工作目錄（通常是 `/workspace/F5-TTS`，即你的專案根目錄）內。  
這樣當 Docker 容器啟動時，`CMD ["uvicorn", "inference:app", ...]` 才能正確找到並執行這個 API 服務。

### 實際流程
1. 你在本機或雲端專案資料夾（如 `F5-TTS`）下建立好 `inference.py`。
2. 用 Dockerfile 把整個專案（包含 `inference.py`）複製進映像檔。
3. 部署到 AWS 時，SageMaker 會根據映像檔啟動容器，並自動執行 `inference.py` 提供 API 服務。

**總結：**  
`inference.py` 必須在你 build Docker image 前就放在專案資料夾裡，這樣才會被包進映像檔，AWS SageMaker 啟動時才能正常提供 API 服務。

## inference.py 應該要寫什麼？（內容說明）

`inference.py` 主要負責以下幾件事：

1. **載入模型**  
   初始化 F5-TTS 模型（如 `tts = F5TTS(model="F5TTS_v1_Base")`）。

2. **定義 API 輸入資料結構**  
   使用 Pydantic 的 `BaseModel` 定義輸入欄位，例如 text、ref_audio、ref_text。

3. **建立 FastAPI 應用**  
   建立 FastAPI app 實例。

4. **撰寫 API 路由**  
   定義 `/tts` 路徑的 POST 方法，接收 JSON 輸入，呼叫模型推論，並回傳語音結果（可為 base64 或檔案）。

5. **（選擇性）處理參考音頻**  
   若有 ref_audio/ref_text，需解析並傳給模型。

### 範例架構

```python
from fastapi import FastAPI
from pydantic import BaseModel
from f5_tts.api import F5TTS

app = FastAPI()
tts = F5TTS(model="F5TTS_v1_Base")

class TTSRequest(BaseModel):
    text: str
    ref_audio: str = None  # base64/URL/路徑，依需求
    ref_text: str = None

@app.post("/tts")
async def tts_api(req: TTSRequest):
    # 依需求處理 ref_audio/ref_text
    wav, sr = tts.infer(req.text)  # 若模型支援 ref_audio/ref_text 可傳入
    # 將 wav 轉 base64 或檔案流回傳
    return {"status": "ok"}
```

### 注意事項
- 你可以根據需求擴充輸入欄位與推論邏輯。
- 若要回傳語音檔案，建議轉成 base64 或直接回傳二進位流。
- 只要 API handler 能正確處理輸入與回傳，SageMaker 就能對外提供服務。

**總結：**  
`inference.py` 就是你自訂的 TTS API 入口，內容可依需求調整，範例僅供參考。

## 如果要修改功能怎麼辦？

如果你想修改 API 行為（例如新增參數、改變推論邏輯、調整回傳格式等），請依下列步驟：

1. 在本機專案資料夾（如 `F5-TTS`）修改 `inference.py` 或其他相關程式碼。
2. 重新執行 `docker build ...` 指令，產生新的 Docker 映像檔（包含你剛剛的修改）。
3. 將新的映像檔重新 tag 並 push 到 AWS ECR。
4. 在 SageMaker 控制台更新（或重建） Endpoint，讓它使用新的映像檔。

這樣 AWS 上的服務就會套用你最新的功能與程式碼。

## 3. 推送映像檔到 AWS ECR
- 登入 AWS ECR（Elastic Container Registry），建立 repository。
- 將本地建好的映像檔 tag 並 push 到 ECR，讓 SageMaker 能拉取使用。

## 4. 建立 SageMaker Endpoint
- 在 SageMaker 控制台建立自定義推論端點，選擇剛剛 push 上去的 ECR 映像檔。
- 設定 instance 規格，啟動 Endpoint，等待狀態變為 InService。

## 什麼是 Endpoint？

Endpoint（端點）是 AWS SageMaker 部署後提供給外部應用程式存取的 API 服務網址。  
當你建立 SageMaker Endpoint 時，SageMaker 會根據你提供的 Docker 映像檔啟動一個容器，並將這個容器的 API 服務（例如 FastAPI）對外開放一個 HTTP 網址。  
你可以透過這個 Endpoint URL 發送 HTTP 請求（如 POST `/tts`），即時取得模型推論結果。

簡單來說，Endpoint 就是「你在雲端部署好的模型 API 服務入口網址」。

這個 Endpoint 可以讓 Bedrock LLM 或其他應用程式直接把產生的文字（text）傳進來，讓你的 TTS 服務即時將文字轉成語音，實現 LLM-to-TTS 的自動串接。

## 5. 提供 API 服務
- Endpoint 啟動後，會自動執行 Docker 容器，並啟動 FastAPI 服務。
- 你可以透過 HTTP POST 請求（如 `/tts` 路徑）呼叫 API，將文字轉成語音。

## 6. 串接 LLM 或應用
- TTS API 的輸入 `text` 欄位可直接接收 Bedrock LLM 或其他應用產生的文本，實現 LLM-to-TTS 串接。

---

## 如何控制參考音頻與文本？

你可以透過呼叫 SageMaker Endpoint 時，POST 的 JSON 內容來控制參數。例如：

```json
{
  "text": "要合成的文字",
  "ref_audio": "base64或URL或檔案路徑",
  "ref_text": "參考音頻的文字內容"
}
```

- `text`：要讓 TTS 合成的目標文本（通常由 LLM 輸出）。
- `ref_audio`：參考音頻（可用 base64 編碼、URL 或檔案路徑，依你的 API 設計）。
- `ref_text`：參考音頻對應的文字（可選，視模型需求）。

你需要在 `inference.py` 的 API handler 裡設計好這些欄位的解析與處理邏輯。  
只要 API 支援這些欄位，呼叫 Endpoint 時就能靈活控制參考音頻與文本。

---

## 總結
你在 AWS 上完成了：
- 建立運算環境
- 打包模型與 API 成 Docker 映像
- 上傳映像到 ECR
- 用 SageMaker 部署成可即時呼叫的 API 服務

這樣就能讓外部應用（如對話機器人、LLM）即時取得語音合成結果。
