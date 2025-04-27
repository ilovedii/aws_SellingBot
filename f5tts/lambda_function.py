import boto3
import json
import uuid
from datetime import datetime
from merge_logs import merge_session_logs
from analysis_agent import call_agent_analysis_lambda
# 導入 TTS 服務
from tts_service import synthesize_speech

# 設定
BUCKET_NAME = 'agent-conversation-logs-clairetest'
REGION = 'us-west-2'
AGENT_ID = 'XGLFHI6VPO'
AGENT_ALIAS_ID = 'BDCPIDGFEK'

# 初始化 client
agent_client = boto3.client('bedrock-agent-runtime', region_name=REGION)
s3_client = boto3.client('s3', region_name=REGION)


def lambda_handler(event, context):
    print("🚀 Event收到的是：", event)
    if isinstance(event, dict) and 'action' in event:
        # 如果直接是 dict 格式（像Test Event這樣）
        body = event
    else:
        # 否則是 API Gateway來的，要parse event['body']
        body = json.loads(event.get('body', '{}'))
    
    action = body.get('action', '').strip().lower()
    print("🚀 action收到的是：", action)
    print(f"🚀 action收到的是：[ {action} ]")
    session_id = body.get('sessionId', str(uuid.uuid4()))
    user_message = body.get('message', '')

    try:
        if action == 'invoke_agent':
            print("action == invoke_agent")
            return invoke_agent(user_message, session_id)

        elif action == 'log_conversation':
            return log_conversation(user_message, session_id)

        elif action == 'end_session':
            return end_session(session_id)

        elif action == 'delete_session':
            return delete_session(session_id)

        else:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Unknown action'})
            }
    except Exception as e:
        print(f"❌ 發生錯誤：{str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

# --- 各個功能分開寫 ---

def invoke_agent(user_message, session_id):
    print(f"👤 User輸入: {user_message}")
    response = agent_client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText=user_message
    )
    
    agent_reply = ""

    # 正確讀取 EventStream
    for event in response['completion']:
        if 'chunk' in event:
            part = event['chunk']['bytes']
            agent_reply += part.decode('utf-8')

    print(f"✅ Agent回覆: {agent_reply}")

    # 呼叫 TTS 將文字轉換為語音 (使用導入的 TTS 服務)
    audio_info = synthesize_speech(agent_reply, session_id)

    # 自動順便 log 這次對話到 S3
    log_conversation_internal(session_id, user_message, agent_reply)

    # 將音頻信息加到回傳結果中
    return {
        'statusCode': 200,
        'body': json.dumps({
            'reply': agent_reply,
            'sessionId': session_id,
            'audioUrl': audio_info.get('audioUrl'),
            'audioStatus': audio_info.get('status')
        }, ensure_ascii=False)
    }

def log_conversation(user_message, session_id):
    # 單純記錄用，沒有呼叫agent
    agent_reply = "手動紀錄"  # 可以改成需要的內容
    log_conversation_internal(session_id, user_message, agent_reply)
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Conversation logged.'})
    }

def log_conversation_internal(session_id, user_message, agent_reply):
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'sessionId': session_id,
        'userInput': user_message,
        'agentReply': agent_reply
    }
    log_key = f'logs/{session_id}/{uuid.uuid4()}.json'
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=log_key,
        Body=json.dumps(log_entry,  ensure_ascii=False),
        ContentType='application/json'
    )
    print(f"✅ 對話紀錄儲存到 {log_key}")

def end_session(session_id):
    # 1. 合併所有 logs 成 summary.json
    merge_session_logs(session_id)

    # 2. 呼叫分析Lambda處理 summary.json
    call_agent_analysis_lambda(session_id)

    # 3. 正式結束 Bedrock Agent 的 session
    print(f"✅ Session資料合併並分析完成: {session_id}")

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Session ended, logs merged and analyzed.'})
    }

def delete_session(session_id):
     # 自己刪 S3 上所有 logs/{sessionId}/ 小檔案
    prefix = f'logs/{session_id}/'
    continuation_token = None

    while True:
        if continuation_token:
            list_response = s3_client.list_objects_v2(
                Bucket=BUCKET_NAME,
                Prefix=prefix,
                ContinuationToken=continuation_token
            )
        else:
            list_response = s3_client.list_objects_v2(
                Bucket=BUCKET_NAME,
                Prefix=prefix
            )

        if 'Contents' not in list_response:
            print(f"⚠️ 沒找到要刪的檔案: {prefix}")
            break

        objects_to_delete = [{'Key': obj['Key']} for obj in list_response['Contents']]

        if objects_to_delete:
            s3_client.delete_objects(
                Bucket=BUCKET_NAME,
                Delete={'Objects': objects_to_delete}
            )
            print(f"✅ S3刪除完成 {len(objects_to_delete)} 筆，sessionId: {session_id}")

        if list_response.get('IsTruncated'):
            continuation_token = list_response.get('NextContinuationToken')
        else:
            break

    print(f"✅ Session資料在S3刪除完成: {session_id}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Session S3 logs deleted.'})
    }