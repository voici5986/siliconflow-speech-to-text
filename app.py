# app.py

from flask import Flask, render_template, request, jsonify
import requests
import os
import time
import re
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# --- 服务配置 ---
# S2T (Speech-to-Text)
S2T_API_URL = os.environ.get('S2T_API_URL', 'https://api.siliconflow.cn/v1/audio/transcriptions')
S2T_API_KEY = os.environ.get('S2T_API_KEY')
S2T_MODEL = os.environ.get('S2T_MODEL', 'FunAudioLLM/SenseVoiceSmall')

# OPT (Optimize Text)
OPT_API_URL = os.environ.get('OPT_API_URL', 'https://api.openai.com/v1/chat/completions')
OPT_API_KEY = os.environ.get('OPT_API_KEY')
OPT_MODEL = os.environ.get('OPT_MODEL')

# --- 分块处理配置 ---
CHUNK_TARGET_SIZE = 5000  # 每个文本块的目标字符数
CHUNK_PROCESSING_THRESHOLD = 5500 # 超过此字符数则启用分块处理
MAX_CONCURRENT_WORKERS = 3 # 并发处理的线程数
RETRY_ATTEMPTS = 3 # 每个块的最大重试次数 (1次初试 + 2次重试)

# --- Prompt ---
HARDCODED_OPTIMIZATION_PROMPT = """
Description:
你是一位录音文字校准专家，能够消除口语表达中的停顿、重复和口语化语气词等常见问题，同时能解决录音软件在记录文字时会产生的错别字、多音字记录不准等技术问题，将口语化的录音文件转换为书面文字。
Background:
在录音转写过程中，录音软件经常会因为口音、语速等原因产生一些错别字、多音字记录不准等问题。
此外，口语表达中的停顿、重复和口语化语气词等也会影响文字的流畅和准确性。
为了将录音文件转写为高质量的书面文字，需要对这些问题进行校准和修正。
Goals:
1.消除录音文字中的停顿、重复和口语化语气词。
2.修正录音文字中的错别字和多音字。
3.确保转写文字保持原文完整性，不遗失任何细节。
4.提供高质量、流畅的书面文字版本。
Constraints:
1.保持原文的完整性，不得删除或遗漏任何信息。
2.仅校准，而不改写任何原文，确保文字内容忠实于原录音。
3.修正错误时需保证语义的准确性和连贯性。
4.校准过程中不得改变原文意思。
5.绝对不会对原文做概括和缩略性的总结，仅仅做出校对。
Skills:
熟悉录音转写的常见问题及其解决方法。
精通中文，能够识别并修正错别字和多音字。
具有良好的语言表达能力，能够将口语化的内容转换为流畅的书面文字。
具备细致入微的校对能力，确保文字的准确性和完整性。
Workflows:
输入: 根据用户提交的录音转化为文字稿。
校准: 消除停顿、重复和口语化语气词，修正错别字和多音字。
输出: 提供校准后的高质量书面文字版本。不要输出任何额外的解释或说明。
检查: 确认修正后的文字保持原文完整性和准确性。
"""

# --- 配置检查 ---
if not S2T_API_KEY:
    print("警告: 环境变量 S2T_API_KEY 未设置。音频转录功能将无法使用。")
if not S2T_API_URL.startswith(('http://', 'https://')):
     print(f"警告: 环境变量 S2T_API_URL 格式不正确: {S2T_API_URL}。音频转录功能可能无法使用。")

opt_configured_for_check = OPT_API_KEY or \
                           (OPT_API_URL and OPT_API_URL != 'https://api.openai.com/v1/chat/completions') or \
                           OPT_MODEL

if opt_configured_for_check:
    print("\n--- OPT 配置检查 ---")
    if not OPT_API_KEY:
        print("警告: 环境变量 OPT_API_KEY 未设置。文本优化功能将无法使用，仅返回原始转录结果。")
    if OPT_API_KEY and (not OPT_API_URL or not OPT_API_URL.startswith(('http://', 'https://'))):
        print(f"警告: 环境变量 OPT_API_URL ({OPT_API_URL}) 无效或格式不正确。文本优化功能可能无法使用。")
    if OPT_API_KEY and not OPT_MODEL:
         print("警告: 已设置 OPT_API_KEY 但未设置 OPT_MODEL。文本优化功能可能无法按预期工作。")
    print("--------------------\n")


@app.route('/')
def index():
    return render_template('index.html')

def _extract_api_error_message(response):
    """辅助函数，从API响应中提取错误信息"""
    try:
        error_detail = response.json()
        api_err_msg = error_detail.get('error', {}).get('message') or \
                      error_detail.get('message') or \
                      error_detail.get('detail')
        if api_err_msg:
            return str(api_err_msg)
        return response.text[:200]
    except ValueError:
        return response.text[:200]

# --- 智能文本分割与上下文处理辅助函数 ---
def _split_text_intelligently(text, chunk_size=CHUNK_TARGET_SIZE):
    """智能分割文本，确保在句子边界分割"""
    if not text or len(text) <= chunk_size:
        return [text] if text else []
    
    delimiters = ['。', '！', '？', '\n']
    chunks = []
    start_index = 0
    
    while start_index < len(text):
        end_index = start_index + chunk_size
        if end_index >= len(text):
            chunks.append(text[start_index:])
            break
        
        best_split_pos = -1
        for d in delimiters:
            pos = text.rfind(d, start_index, end_index)
            if pos > best_split_pos:
                best_split_pos = pos
        
        if best_split_pos != -1:
            chunks.append(text[start_index : best_split_pos + 1])
            start_index = best_split_pos + 1
        else:
            chunks.append(text[start_index:end_index])
            start_index = end_index
            
    return [c for c in chunks if c.strip()]

def _get_last_sentence(text):
    """从文本中获取最后一句话作为上下文"""
    if not text:
        return ""
    sentences = re.split(r'(?<=[。？！\n])', text.strip())
    return sentences[-1].strip() if sentences else ""

def _optimize_chunk_with_retry(chunk_data):
    """处理单个文本块，包含重试和上下文逻辑"""
    text_chunk = chunk_data['text']
    context_sentence = chunk_data.get('context')
    
    messages = [{"role": "system", "content": HARDCODED_OPTIMIZATION_PROMPT}]
    if context_sentence:
        user_content = (
            f"为了保持上下文连贯，这是紧接在当前文本之前的最后一句话：\n---CONTEXT---\n{context_sentence}\n---END CONTEXT---\n\n"
            f"请仅校准并返回以下这段新的文本，不要在你的回答中重复上面的上下文内容：\n---TEXT TO CALIBRATE---\n{text_chunk}\n---END TEXT---"
        )
    else:
        user_content = text_chunk
    messages.append({"role": "user", "content": user_content})

    payload = {'model': OPT_MODEL, 'messages': messages, 'temperature': 0.1}
    headers = {'Authorization': f'Bearer {OPT_API_KEY}', 'Content-Type': 'application/json'}

    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.post(OPT_API_URL, headers=headers, json=payload, timeout=300)
            if response.status_code == 200:
                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                if content:
                    return {"status": "success", "content": content}
                else:
                    return {"status": "error", "message": "API返回空内容"}
            
            error_msg = f"API错误 {response.status_code}: {_extract_api_error_message(response)}"
            if response.status_code in [400, 401, 403, 429]: # 不可重试的客户端错误
                return {"status": "error", "message": error_msg}
            # 对于服务端错误 (e.g., 5xx) 或其他可恢复错误，将继续重试

        except requests.exceptions.Timeout:
            error_msg = "请求超时"
        except requests.exceptions.RequestException as e:
            error_msg = f"网络连接错误: {type(e).__name__}"
        
        if attempt == RETRY_ATTEMPTS - 1:
            return {"status": "error", "message": error_msg}
        
        print(f"块处理失败 (尝试 {attempt + 1}/{RETRY_ATTEMPTS}): {error_msg}. 将在 {2 * (attempt + 1)} 秒后重试...")
        time.sleep(2 * (attempt + 1))

    return {"status": "error", "message": "未知错误，已达最大重试次数"}


# --- 重构核心校准函数 ---
def _perform_text_optimization(raw_text_to_optimize):
    opt_configured_properly = OPT_API_KEY and OPT_API_URL and OPT_API_URL.startswith(('http://', 'https://')) and OPT_MODEL
    
    if not opt_configured_properly:
        skip_reason_parts = []
        if not OPT_API_KEY: skip_reason_parts.append("缺少API Key")
        if not OPT_API_URL or not OPT_API_URL.startswith(('http://', 'https://')): skip_reason_parts.append("API URL无效")
        if not OPT_MODEL: skip_reason_parts.append("缺少模型名称")
        
        if not opt_configured_for_check:
             opt_status_message = "校准已跳过 (服务未配置)"
        else:
            skip_reason = ", ".join(skip_reason_parts)
            opt_status_message = f"校准已跳过 (服务配置不完整: {skip_reason})"
        print(f"OPT API 配置不完整，跳过文本优化。原因: {opt_status_message}")
        return raw_text_to_optimize, opt_status_message, False

    if len(raw_text_to_optimize) <= CHUNK_PROCESSING_THRESHOLD:
        print("文本较短，直接进行单次校准...")
        result = _optimize_chunk_with_retry({'text': raw_text_to_optimize})
        if result['status'] == 'success':
            return result['content'], "校准成功！", True
        else:
            return raw_text_to_optimize, f"校准失败 ({result['message']})", False
            
    print(f"文本过长({len(raw_text_to_optimize)}字)，启动分块并发校准...")
    chunks = _split_text_intelligently(raw_text_to_optimize)
    if not chunks:
        return raw_text_to_optimize, "校准失败 (文本分割后为空)", False
        
    print(f"文本被分割为 {len(chunks)} 块，使用 {MAX_CONCURRENT_WORKERS} 个并发进行处理。")
    
    tasks = []
    for i, chunk in enumerate(chunks):
        prev_chunk_context = _get_last_sentence(chunks[i-1]) if i > 0 else None
        tasks.append({'text': chunk, 'context': prev_chunk_context})

    processed_results = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS) as executor:
        results_iterator = executor.map(_optimize_chunk_with_retry, tasks)
        processed_results = list(results_iterator)

    failed_chunks = [res for res in processed_results if res['status'] == 'error']
    if failed_chunks:
        first_error_message = failed_chunks[0]['message']
        print(f"校准过程中有块处理失败，回退到原始文本。失败原因: {first_error_message}")
        return raw_text_to_optimize, f"校准失败 ({first_error_message})", False
    else:
        full_optimized_text = "".join([res['content'] for res in processed_results])
        print("所有块均已成功校准并合并。")
        return full_optimized_text, "校准成功！", True

# --- 路由部分 (调用已封装的逻辑) ---
@app.route('/transcribe', methods=['POST'])
def transcribe_and_optimize_audio():
    audio_file = request.files.get('audio_file')
    if not audio_file:
        return jsonify({"error": "缺少上传的音频文件"}), 400

    print("开始调用 S2T API 进行转录...")
    if not S2T_API_KEY:
         return jsonify({"error": "服务器配置错误：缺少 S2T API Key"}), 500
    if not S2T_API_URL.startswith(('http://', 'https://')):
        return jsonify({"error": "服务器配置错误：S2T API 端点 URL 格式不正确"}), 500

    raw_transcription = ""
    try:
        s2t_files = {'file': (audio_file.filename, audio_file.stream, audio_file.mimetype)}
        s2t_payload = {'model': S2T_MODEL}
        s2t_headers = {'Authorization': f'Bearer {S2T_API_KEY}'}
        s2t_response = requests.post(S2T_API_URL, files=s2t_files, data=s2t_payload, headers=s2t_headers, timeout=300)

        if s2t_response.status_code == 200:
            try:
                s2t_data = s2t_response.json()
                raw_transcription = s2t_data.get('text', '').strip()
                if not raw_transcription:
                    print("S2T API 返回空文本")
                    return jsonify({"error": "S2T 服务未能识别出任何文本。"}), 500
                print(f"S2T 转录成功，原始文本长度: {len(raw_transcription)}")
            except ValueError:
                 return jsonify({"error": "无法解析 S2T API 响应"}), 500
        else:
            error_details = _extract_api_error_message(s2t_response)
            s2t_error_message = f"S2T API 返回错误: {s2t_response.status_code} - {error_details}"
            print(s2t_error_message)
            return jsonify({"error": s2t_error_message}), 500
            
    except requests.exceptions.Timeout:
        return jsonify({"error": "调用 S2T API 超时，请稍后再试或检查文件大小。"}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"调用 S2T API 时发生连接错误: {str(e)}"}), 500
    except Exception as e:
        print(f"处理 S2T 请求时发生未知错误: {e}")
        return jsonify({"error": f"处理 S2T 请求时发生未知错误: {type(e).__name__}"}), 500

    final_transcription, opt_message, is_calibrated = _perform_text_optimization(raw_transcription)
    
    if is_calibrated:
        final_status_message = f"转录完成，{opt_message}"
    elif "跳过" in opt_message:
        final_status_message = f"转录完成 ({opt_message.replace('校准已跳过', '校准服务')})" 
    else:
        final_status_message = f"转录完成，{opt_message.replace('校准失败', '但校准失败')}"

    return jsonify({
        "status": "success",
        "transcription": final_transcription,
        "raw_transcription": raw_transcription,
        "calibration_message": final_status_message,
        "is_calibrated": is_calibrated
    })

@app.route('/recalibrate', methods=['POST'])
def recalibrate_text():
    data = request.get_json()
    if not data or 'raw_transcription' not in data:
        return jsonify({"error": "请求体无效或缺少 raw_transcription 字段"}), 400
        
    raw_text = data.get('raw_transcription')
    if not isinstance(raw_text, str) or not raw_text.strip():
        return jsonify({"error": "需要重新校准的文本不能为空"}), 400

    print(f"收到重新校准请求，文本长度: {len(raw_text)}")
    
    calibrated_text, calibration_status_msg, calibration_success = _perform_text_optimization(raw_text)

    return jsonify({
        "status": "success",
        "transcription": calibrated_text,
        "calibration_message": calibration_status_msg,
        "is_calibrated": calibration_success
    })


if __name__ == '__main__':
    from waitress import serve
    print("服务器正在启动，监听 http://0.0.0.0:5000")
    serve(app, host='0.0.0.0', port=5000)
