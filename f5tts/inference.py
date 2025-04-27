from fastapi import FastAPI, Request
from pydantic import BaseModel
from f5_tts.api import F5TTS

app = FastAPI()
tts = F5TTS(model="F5TTS_v1_Base")

class TTSRequest(BaseModel):
    text: str           # LLM 輸出文本
    ref_audio: str = None  # 參考音頻（可 base64/URL/路徑，依模型支援）

@app.post("/tts")
async def tts_api(req: TTSRequest):
    # 若模型支援 ref_audio，請傳入
    wav, sr = tts.infer(req.text, ref_audio=req.ref_audio)
    # 回傳音檔（建議轉 base64 或檔案流，這裡僅示意）
    return {"status": "ok"}

# 這樣設計後，你的 /tts API 可以直接接收 Bedrock LLM 輸出的文本（text 欄位），
# 以及參考音頻（ref_audio），然後進行語音合成。
# 只要 Bedrock LLM 的輸出格式與這個 API 的輸入格式一致（JSON 內有 text 欄位），
# 就可以直接串接使用.
