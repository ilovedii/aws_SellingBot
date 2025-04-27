FROM nvidia/cuda:12.4.0-base-ubuntu22.04

# 安裝必要的套件
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ml/code

# 複製專案檔案
COPY . .

# 安裝專案相依套件
RUN pip3 install --no-cache-dir -r requirements.txt

# 確保 serve 腳本有執行權限
RUN chmod +x serve

# 設定健康檢查路由
HEALTHCHECK CMD curl --fail http://localhost:8080/ping || exit 1

# 暴露 SageMaker 使用的預設端口
EXPOSE 8080

# 容器啟動命令
ENTRYPOINT ["./serve"]
