# F5-TTS SageMaker 部署執行步驟

## 1. 安裝 AWS CLI

- Windows 可用 pip 安裝：
  ```bash
  pip install awscli --upgrade --user
  ```
- 驗證安裝：
  ```bash
  aws --version
  ```

## 2. 設定 AWS CLI

- 執行：
  ```bash
  aws configure
  ```
- 輸入 Access Key ID、Secret Access Key、region（如 ap-northeast-1）、output format（建議 json）

## 3. 建立 ECR repository

- 建議名稱：`f5tts-api`
  ```bash
  aws ecr create-repository --repository-name f5tts-api
  ```

## 4. 登入 ECR

- 執行（請換成你的 region 和帳號）：
  ```bash
  aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 972401528146.dkr.ecr.us-west-2.amazonaws.com
  ```

## 5. Build 並推送 Docker 映像檔

- 確保 Dockerfile 正確配置，包含以下必要元素：
  ```dockerfile
  # 建議使用 NVIDIA GPU 基礎映像
  FROM nvidia/cuda:12.4.0-base-ubuntu22.04
  
  # 安裝必要的套件
  RUN apt-get update && apt-get install -y \
      python3 \
      python3-pip \
      ffmpeg \
      libsndfile1 \
      && rm -rf /var/lib/apt/lists/*
  
  WORKDIR /opt/ml/code
  
  # 安裝專案相依套件
  COPY requirements.txt .
  RUN pip3 install -r requirements.txt
  
  # 確保安裝 AWS 相關套件
  RUN pip3 install boto3 pydantic fastapi uvicorn soundfile
  
  # 複製專案檔案
  COPY . .
  
  # 建立 serve 腳本 (SageMaker 需要)
  RUN chmod +x serve
  
  # 設定環境變數
  ENV PATH="/opt/ml/code:${PATH}"
  
  # 容器啟動命令
  ENTRYPOINT ["./serve"]
  ```

- 在專案根目錄建立 `requirements.txt`，確保包含以下項目：
  ```
  torch>=2.0.0
  torchaudio>=2.0.0
  numpy
  matplotlib
  omegaconf
  hydra-core
  ffmpeg-python
  cached-path
  soundfile
  boto3
  pydantic
  fastapi
  uvicorn
  transformers
  pydub
  vocos
  huggingface_hub
  ```

- 在專案根目錄建立 `serve` 腳本：
  ```bash
  #!/bin/bash
  
  # 啟動模型服務
  exec uvicorn inference:app --host 0.0.0.0 --port 8080
  ```

- 在專案根目錄確保 `inference.py` 包含 SageMaker 所需的端點：
  ```python
  # SageMaker 需要的健康檢查端點
  @app.get("/ping")
  def ping():
      return {"status": "ok"}
      
  # SageMaker 需要的推理端點
  @app.post("/invocations")
  async def invocations(request: Request):
      # 從請求獲取資料
      data = await request.json()
      text = data.get("text", "")
      
      # 呼叫您現有的 TTS 模型處理函數
      audio_data = your_existing_tts_function(text)
      
      # 返回結果
      return {"audio": audio_data}
  ```
  
  > **注意**：以上的 inference.py 範例只包含 SageMaker 所需的新端點。
  > 若您已有 inference.py，只需添加這兩個端點（/ping 和 /invocations）
  > 到現有檔案中，並確保它們使用您實際的 F5-TTS 模型處理邏輯。

- 在 F5-TTS 目錄下 build：
  ```bash
  docker build -t f5tts:v1 .
  ```
- Tag 映像檔（請換成你的帳號/region）：
  ```bash
  docker tag f5tts:v1 972401528146.dkr.ecr.us-west-2.amazonaws.com/f5tts-api:v1
  ```
- Push 到 ECR：
  ```bash
  docker push 972401528146.dkr.ecr.us-west-2.amazonaws.com/f5tts-api:v1
  ```

## 6. 建立 SageMaker Endpoint

- 到 AWS 管理台 > SageMaker > Inference > Endpoints > Create endpoint
- 選自定義容器，填入剛剛 push 上去的 ECR image
- 選擇 GPU instance type（如 ml.g4dn.xlarge）
- 設定環境變數（如需要）：
  ```
  NVIDIA_VISIBLE_DEVICES=all
  ```
- 重要：為 SageMaker 執行角色添加必要權限
  - 前往 IAM > 角色 > 找到你的 SageMaker 執行角色
  - 添加以下政策：
    - `AmazonS3FullAccess`（或自訂限制範圍的 S3 存取權限）
    - 如需使用 Bedrock，添加 `AmazonBedrockFullAccess`（或適當限制的自訂政策）

- 啟動 endpoint

## 7. 測試 API

- 取得 endpoint URL，測試基本 TTS 功能：
  ```bash
  curl -X POST \
    -H "Content-Type: application/json" \
    -d '{"text":"你好，這是測試"}' \
    https://<endpoint-id>.sagemaker-endpoint.<region>.amazonaws.com/invocations
  ```

- 測試帶 S3 參考音頻的整合功能：
  ```bash
  curl -X POST \
    -H "Content-Type: application/json" \
    -d '{
      "text":"這是由 Bedrock LLM 生成的文本", 
      "ref_audio_bucket":"my-audio-bucket", 
      "ref_audio_key":"references/sample.wav", 
      "output_bucket":"my-output-bucket", 
      "output_key":"generated/output.wav"
    }' \
    https://<endpoint-id>.sagemaker-endpoint.<region>.amazonaws.com/invocations
  ```

## 8. 故障排除

如果遇到 "primary container did not pass the ping health check" 錯誤：

1. 檢查容器日誌：
   - 在 SageMaker 控制台找到 endpoint 名稱
   - 點擊 "Model container logs" 連結或前往 CloudWatch 查看日誌

2. NVIDIA Driver 未檢測到的問題：
   - 確保選擇了 GPU 實例類型（ml.g4dn.xlarge 等）
   - 確保 Dockerfile 正確設定了 CUDA 環境

3. "serve: not found" 錯誤：
   - 確認 `serve` 腳本存在且有執行權限 (chmod +x serve)
   - 確認 ENTRYPOINT 設置正確指向了 serve 腳本

4. 測試容器本地執行：
   ```bash
   docker run --rm -it f5tts:v1
   ```
   確保容器能正常啟動並提供服務

---
