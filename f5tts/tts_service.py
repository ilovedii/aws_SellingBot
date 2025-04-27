import boto3
import json
from datetime import datetime

# TTS 設定 (可自定義這些常數)
REGION = 'us-west-2'  # AWS 區域
TTS_ENDPOINT_NAME = 'f5tts-endpoint'  # SageMaker endpoint 名稱
TTS_INPUT_BUCKET = 'f5tts-input-m4a'  # 存放參考音頻的 bucket
TTS_OUTPUT_BUCKET = 'f5tts-output-wav'  # 存放輸出音頻的 bucket
TTS_REF_AUDIO_KEY = 'reference_voice.wav'  # 參考音頻檔案的 key

# 初始化 client
s3_client = boto3.client('s3', region_name=REGION)
sagemaker_client = boto3.client('sagemaker-runtime', region_name=REGION)


class TTSService:
    """語音合成服務類，提供 LLM 文本轉語音功能"""
    
    def __init__(
        self, 
        endpoint_name=TTS_ENDPOINT_NAME,
        input_bucket=TTS_INPUT_BUCKET, 
        output_bucket=TTS_OUTPUT_BUCKET,
        ref_audio_key=TTS_REF_AUDIO_KEY,
        region=REGION
    ):
        """初始化 TTS 服務
        
        Args:
            endpoint_name: SageMaker TTS endpoint 名稱
            input_bucket: 存放參考音頻的 S3 bucket
            output_bucket: 存放輸出音頻的 S3 bucket
            ref_audio_key: 參考音頻的 S3 key
            region: AWS 區域
        """
        self.endpoint_name = endpoint_name
        self.input_bucket = input_bucket
        self.output_bucket = output_bucket
        self.ref_audio_key = ref_audio_key
        self.region = region
        
        # 使用傳入的 region 初始化客戶端
        self.s3_client = boto3.client('s3', region_name=region)
        self.sagemaker_client = boto3.client('sagemaker-runtime', region_name=region)
        
    def synthesize_speech(self, text, session_id=None, output_key=None):
        """將文本轉換為語音
        
        Args:
            text: 待合成的文本
            session_id: 會話ID (用於生成唯一文件名)
            output_key: 自訂輸出檔案路徑，若不指定會自動生成
            
        Returns:
            包含合成結果的字典，包括音頻URL和狀態
        """
        try:
            # 生成唯一的輸出檔案名
            if not output_key:
                timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
                session_path = f"{session_id}/" if session_id else ""
                output_key = f'audio/{session_path}{timestamp}.wav'
            
            # 準備要傳給 TTS endpoint 的資料
            tts_payload = {
                "text": text,
                "ref_audio_bucket": self.input_bucket,
                "ref_audio_key": self.ref_audio_key,
                "output_bucket": self.output_bucket,
                "output_key": output_key
            }
            
            # 呼叫 SageMaker endpoint
            print(f"🔊 呼叫 TTS 服務，文本長度: {len(text)} 字元")
            tts_response = self.sagemaker_client.invoke_endpoint(
                EndpointName=self.endpoint_name,
                ContentType='application/json',
                Body=json.dumps(tts_payload)
            )
            
            # 解析回應
            tts_result = json.loads(tts_response['Body'].read().decode())
            print(f"✅ TTS 處理完成: {tts_result}")
            
            # 生成可訪問的 S3 URL (預設 15 分鐘有效)
            audio_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.output_bucket,
                    'Key': output_key
                },
                ExpiresIn=900  # 15分鐘
            )
            
            return {
                'status': 'success',
                'audioUrl': audio_url,
                's3Path': f's3://{self.output_bucket}/{output_key}',
                'details': tts_result
            }
            
        except Exception as e:
            print(f"❌ TTS 處理失敗: {str(e)}")
            return {
                'status': 'error',
                'error': str(e),
                'audioUrl': None
            }


# 便捷函數，使用默認設定
def synthesize_speech(text, session_id=None):
    """便捷函數：使用默認設定進行語音合成
    
    Args:
        text: 待合成的文本
        session_id: 會話ID (用於生成唯一文件名)
    
    Returns:
        包含合成結果的字典，包括音頻URL和狀態
    """
    tts_service = TTSService()
    return tts_service.synthesize_speech(text, session_id)