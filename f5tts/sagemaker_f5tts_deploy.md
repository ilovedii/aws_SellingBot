# F5-TTS 預訓練模型於 AWS SageMaker 部署規劃書

## 目標
將 F5-TTS 預訓練模型部署於 AWS SageMaker，提供即時 TTS（文字轉語音）API 服務，供對話機器人等應用串接。

---

## 步驟一：AWS SageMaker 環境準備

1. 登入 AWS 管理台。
2. 進入 SageMaker 服務頁面。
3. 建立 Notebook Instance 或 SageMaker Studio，並選擇 GPU instance（例如 `ml.g4dn.xlarge`）。
4. IAM role 請選擇「AmazonSageMaker-ExecutionRole」或建立一個同時擁有 SageMaker、S3、ECR 權限的角色（建議用精靈建立，並附加 AmazonSageMakerFullAccess、AmazonS3FullAccess、AmazonEC2ContainerRegistryFullAccess）。

---

## 步驟二：準備 F5-TTS 及 Docker 環境

1. 直接使用 F5-TTS repo 內的 Dockerfile（`F5-TTS/Dockerfile`），不需自行重寫。
2. 在 Dockerfile 內補充 FastAPI 與 Uvicorn 安裝：
   ```dockerfile
   RUN pip install fastapi uvicorn
   ```
3. 在 Dockerfile 內補充啟動 API 指令（假設 inference.py 在 F5-TTS 目錄下）：
   ```dockerfile
   CMD ["uvicorn", "inference:app", "--host", "0.0.0.0", "--port", "8000"]
   ```
4. 若要本地測試，可用下列指令建構映像檔（在 F5-TTS 目錄下）：
   ```bash
   docker build -t f5tts:v1 .
   ```

---

### 補充：WSL 與 PowerShell 同時 build

你可以在 WSL（Linux 子系統）和 PowerShell（Windows）上分別執行 `docker build`，但這兩個環境預設共用同一個 Docker Engine（如果你安裝的是 Docker Desktop），所以建構出來的映像檔會在同一個本地 Docker 映像庫中。

- **同時 build**：可以，但建議不要同時對同一個專案資料夾進行 build，避免檔案鎖定或衝突。
- **建議**：選擇一個環境（WSL 或 PowerShell）來 build 即可，除非你有特殊需求。

---

### 建議：等待 build 時可以先做什麼？

- 準備好 `inference.py`，確認 API 輸入/輸出格式與功能都符合需求。
  - 你的需求是：API 要能接收 Bedrock LLM 輸出的文本（通常是 JSON 內的 `text` 欄位），並將其轉為語音。
  - 請確保 `inference.py` 的 API 路由（如 `/tts`）能正確處理這個欄位，並回傳語音結果（如 base64 或檔案流）。
- 準備好 AWS ECR repository（可先在 AWS 管理台建立好）。
  - **ECR repository 建立時建議設定：**
    - Repository name：自訂名稱（如 f5tts），建議小寫、可用 `-` 分隔。
      - 建議名稱範例：`f5tts-api`、`f5tts-sagemaker`、`f5tts-prod`、`f5tts-demo`
    - Image tag mutability：預設選 Mutable（可覆蓋 tag，方便後續更新）。
    - Encryption：預設 AES-256 即可（不用特別改動）。
    - 其他選項可維持預設，除非有特殊安全需求。
  - 建立後會得到 repository URL，後續 push 映像檔時會用到。
- 準備好 SageMaker Endpoint 相關設定（如 IAM 權限、instance 規格）。
  - **SageMaker Endpoint 設定建議：**
    - IAM 權限：使用有 SageMaker 執行權限的 IAM Role（如 AmazonSageMaker-ExecutionRole），需同時有 S3、ECR 權限。
    - Instance 規格：依模型需求選擇 GPU（如 `ml.g4dn.xlarge`）或 CPU（如 `ml.m5.large`），建議先用 GPU 測試。
    - Endpoint 名稱：自訂名稱（如 `f5tts-endpoint`）。
    - 其他設定可維持預設，若有特殊需求（如 VPC、加密）可依需求調整。
    - 可於 SageMaker 控制台 > Inference > Endpoints > Create endpoint 建立。
- 撰寫/測試串接 Bedrock LLM 的程式碼或流程。
- 規劃 API 測試腳本（如 curl、Postman 或 Python requests）。
- 檢查 Dockerfile 內容、requirements.txt 是否正確。

這樣 build 完成後，可以無縫接續後續步驟，節省整體部署時間。

---

## 步驟三：API 服務包裝

1. 在 `F5-TTS` 目錄下建立 `inference.py`，用 FastAPI 包裝 F5-TTS 推論（參考下方簡易範例）。
2. API 路徑如 `/tts`，POST 輸入 JSON：`{"text": "你好"}`，回傳語音檔案或 base64。

---

## 步驟四：建構與推送 Docker 映像檔

1. 本地 build Docker image（在 F5-TTS 目錄下）：
   ```bash
   docker build -t f5tts:v1 .
   ```
2. 登入 AWS ECR，建立 repository（若尚未建立），並取得對應的 ECR 登入指令與 repository 位址。

   - **ECR（Elastic Container Registry）** 是 AWS 的 Docker 映像檔倉庫，你需要先建立一個 repository 來存放你的映像檔。
   - 如果你想用 CLI 完成，步驟如下：

     **1. 安裝 AWS CLI**
     - 參考官方文件：https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
     - Windows 可下載安裝程式，或用 pip 安裝：
       ```bash
       pip install awscli --upgrade --user
       ```
     - 安裝後，打開終端機（PowerShell、CMD 或 WSL），輸入 `aws --version` 應該會看到版本號。

     **2. 設定 AWS CLI**
     - 執行：
       ```bash
       aws configure
       ```
     - 依序輸入你的 AWS Access Key ID、Secret Access Key、region（如 ap-northeast-1）、output format（可填 json）。
       - output format 建議填 `json`（預設即可），也可填 `text` 或 `table`，但 `json` 最通用。
       - 若不確定，直接按 Enter 使用預設值（通常是 `json`）即可。

     **3. 建立 ECR repository**
     - 執行（將 `f5tts-api` 換成你的 repo 名稱）：
       ```bash
       aws ecr create-repository --repository-name f5tts-api
       # 若出現 "The security token included in the request is invalid."，代表 AWS CLI 沒有正確設定或金鑰過期/錯誤。
       # 請檢查：
       # 1. 你輸入的 Access Key ID/Secret Access Key 是否正確（建議重新執行 aws configure）。
       # 2. IAM 使用者是否有 ECR 權限。
         - 你目前 aws configure 設定的 Access Key/Secret Key 是否正確（建議重新執行 aws configure 並貼上新產生的金鑰）。
         - 你有沒有切換到正確的 AWS CLI profile（如果有多組帳號）。
         - 你的金鑰是否已被停用、刪除或過期（可到 IAM > Users > Security credentials 檢查）。
         - 若你有啟用 MFA 或臨時憑證，請確認 token 未過期。
         - 可先執行 `aws sts get-caller-identity` 測試 CLI 是否能正確連線 AWS，若此指令也報錯，代表金鑰或設定仍有問題。
           - **此錯誤（InvalidClientTokenId）通常表示你設定的 Access Key/Secret Key 有誤、過期、被刪除或是貼錯帳號。**
           - 請到 AWS 管理台 > IAM > Users > Security credentials，重新產生一組 Access Key，並用 `aws configure` 重新設定。
           - 建議刪除本機 `~/.aws/credentials` 檔案後再設定一次，避免殘留錯誤金鑰。
           - 請確認你貼入的是「使用者」的 Access Key（不要用 root 帳號），且該使用者有對應權限。
           - 設定完畢後再次執行 `aws sts get-caller-identity`，應該會顯示你的帳號資訊。
       ```

       補充說明：
       你不需要啟用 Console password（Enable console access）來產生 Access Key。
       Access Key 是在 IAM > Users > Security credentials 頁面下方的「Access keys」區塊產生，與 Console 登入密碼無關。
       只要有 Access Key ID/Secret Access Key，就能用 AWS CLI 操作，不需啟用 Console password。
       Console password 只用於網頁登入 AWS 管理台，與 CLI 無直接關係。

     **4. 登入 ECR**
     - 執行（將 `<region>`、`<aws_account_id>` 換成你的實際值）：
       ```bash
       aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.<region>.amazonaws.com
       ```
     - 登入成功會顯示 Login Succeeded。

     **5. Tag 並 push Docker 映像檔**
     - Tag：
       ```bash
       docker tag f5tts:v1 <aws_account_id>.dkr.ecr.<region>.amazonaws.com/f5tts-api:v1
       ```
     - Push：
       ```bash
       docker push <aws_account_id>.dkr.ecr.<region>.amazonaws.com/f5tts-api:v1
       ```

   - 完成後，你的映像檔就會在 ECR repository，可以用於 SageMaker 部署。

---

## 步驟五：SageMaker Endpoint 建立

1. 在 SageMaker 控制台建立自定義推論端點，選擇自定義容器，填入剛剛 push 上去的 ECR image。
2. 設定 instance type（如 `ml.g4dn.xlarge`），啟動 endpoint。
3. 等待 Endpoint 狀態變為 InService（啟動完成）。

---

## 步驟六：API 測試與串接

1. 取得 SageMaker Endpoint URL。
2. 用 curl/Postman 測試：
   ```bash
   curl -X POST -H "Content-Type: application/json" -d '{"text":"你好"}' http://<endpoint-url>/tts
   ```
3. 將 endpoint 串接至對話機器人後端，或直接串接 Bedrock LLM 的輸出文本作為 TTS API 的輸入。

---

## 參考 FastAPI 推論服務範例

```python
# inference.py
from fastapi import FastAPI
from pydantic import BaseModel
from f5_tts.api import F5TTS

app = FastAPI()
tts = F5TTS(model="F5TTS_v1_Base")

class TTSRequest(BaseModel):
    text: str

@app.post("/tts")
async def tts_api(req: TTSRequest):
    wav, sr = tts.infer(req.text)
    # 可將 wav 轉 base64 或直接回傳檔案
    return {"status": "ok"}
```

---

## 常見問題補充

- **Q: 我用 AWS CLI 操作（如 push image、建立 repo），輸出（如映像檔、repo）會自動存在哪裡？**
  - **A:**  
    - 你 push 到 ECR 的 Docker 映像檔會存放在 AWS 雲端的 ECR repository，不會自動存到本地硬碟。
    - 你在本地 build 的 Docker image 會存在本機 Docker 映像庫（用 `docker images` 可查），只有執行 `docker push` 才會上傳到 ECR。
    - 其他 AWS CLI 操作（如建立 repo、啟動 endpoint）都是在 AWS 雲端執行，結果只會在 AWS 管理台/ECR/SageMaker 看到，不會自動存本地。
    - 若 CLI 指令有 `--output` 選項（如 `aws s3 cp`），你可指定本地存檔路徑，否則預設只顯示在終端機。

---

## 備註

- TTS API 的 `text` 欄位建議直接接收 Bedrock LLM 產生的文本，實現 LLM-to-TTS 串接。
- 若需回傳語音檔案，建議將 wav 轉 base64 或直接回傳二進位流。
- 可根據需求擴充 API，例如支援多語言、參數調整等。
- 若需更完整的 Dockerfile 或 inference handler 範例，可再提出。

