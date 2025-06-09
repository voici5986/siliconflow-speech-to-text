from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import requests
import os
import time
import re
import json
from concurrent.futures import ThreadPoolExecutor
from waitress import serve

app = Flask(__name__, static_folder='static', static_url_path='')

# --- 服务配置 ---
S2T_API_URL = os.environ.get('S2T_API_URL', 'https://api.siliconflow.cn/v1/audio/transcriptions')
S2T_API_KEY = os.environ.get('S2T_API_KEY')
S2T_MODEL = os.environ.get('S2T_MODEL', 'FunAudioLLM/SenseVoiceSmall')

OPT_API_URL = os.environ.get('OPT_API_URL', 'https://api.openai.com/v1/chat/completions')
OPT_API_KEY = os.environ.get('OPT_API_KEY')
OPT_MODEL = os.environ.get('OPT_MODEL')

# --- 分块处理配置 ---
CHUNK_TARGET_SIZE = 5000
CHUNK_PROCESSING_THRESHOLD = 5500
MAX_CONCURRENT_WORKERS = 3
RETRY_ATTEMPTS = 3

# --- OpenAI 兼容 API 配置 ---
API_ACCESS_TOKEN = os.environ.get('API_ACCESS_TOKEN')
MODEL_CALIBRATE = "s2t-calibrated"
MODEL_SUMMARIZE = "s2t-summarized"

# --- Prompts ---
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
输出: 提供校准后的高质量书面文字版本。
检查: 确认修正后的文字保持原文完整性和准确性。
"""

PROMPT_SUMMARY_MAP = """
Description:
你是一位信息分析专家，正在执行一个大型文档分析任务的第一步。你的当前任务是，从提供给你的【文档片段】中，高效、精准地提取出所有的核心信息和关键要点。你提取出的要点将作为后续最终摘要整合的【原材料】。
Skills：
1.提炼关键信息：快速识别并提取关键词、主题句或中心思想。
2.逻辑梳理：理解文字的内在逻辑，确保提取的要点条理清晰。
3.分类归类：能够将片段内的相关信息点进行有效归纳。
4.概括提升：在归纳的基础上，提炼出更高层次的概念或结论。
5.精简语言：使用最凝练的语言来表达要点，去除所有不必要的修饰和口语化内容。
Rules：
1.准确全面：提取的要点必须准确反映【文档片段】的核心内容，不能遗漏重要信息。
2.客观中立：仅提取事实和观点，不掺杂个人情绪或进行二次解读。
3.重点突出：把握住片段的重点和主旨，突出核心内容。
Workflows：
1. 仔细阅读用户给出的【文档片段】原文。
2. 根据 <Rules> 对原文进行分析，提取出所有关键信息点。
3. 将这些关键信息点整理成一个无序列表（bullet points）进行输出。
Output Format:
- [要点1]
- [要点2]
- [要点3]
Constraints:
1. 忠于原文，不得改变【文档片段】的原意。
2. 只输出要点列表，不要输出任何额外的标题、开头、结尾、解释或说明。例如，不要写“以下是本文档片段的要点：”。
3. 每个要点都应是独立的、有意义的信息单元。
"""

PROMPT_SUMMARY_REDUCE = """
Description:
你是一位资深的首席编辑，你的任务是将一份由多位助理从一篇长篇录音稿中分段提取的【核心要点清单】进行最终整合，撰写成一份完整、流畅、逻辑清晰的最终摘要，供高层决策者阅读。
Background:
你收到的【核心要点清单】是按原文顺序排列的，但因为是分段提取，所以可能存在轻微的重复、风格不一或上下文断裂的问题。你的专业价值在于消除这些问题，创造出一篇浑然一体的最终作品。
Skills：
1. 全局视野：能够从零散的要点中洞察整个文档的宏观结构和核心主旨。
2. 叙事构建：擅长将独立的要点有机地串联起来，构建出有开头、有主体、有结尾的流畅叙事。
3. 逻辑重构：识别并梳理要点之间的逻辑关系（因果、并列、递进等），形成严密的逻辑链条。
4. 语言润色：使用专业、精炼、书面化的语言，统一全文风格，提升文本的专业性和可读性。
5. 综合概括：在整合所有要点的基础上，进行更高层次的归纳与升华。
Rules：
1. 全面覆盖：最终摘要必须全面反映【核心要点清单】中提供的所有关键信息，不得遗漏。
2. 连贯流畅：摘要的段落和句子之间必须过渡自然，逻辑通顺。
3. 结构清晰：摘要应有引言部分概括主旨，主体部分分点或分段阐述，结论部分进行总结。
4. 客观准确：忠实于要点清单的内容，不添加清单之外的信息或个人主观臆断。
Workflows：
1. 通读并理解整个【核心要点清单】。
2. 在脑海中构思出最终摘要的宏观结构。
3. 开始撰写，将独立的要点无缝地融入到流畅的段落中。
4. 撰写完成后，进行通篇审阅，检查逻辑、流畅性和完整性。
5. 输出最终的、可以直接发布的摘要成品，不要输出任何额外的解释或说明。
Constraints:
1. 绝对不要在摘要中提及“根据提供的要点”、“此清单显示”或“本文档的要点是”这类元语言。你必须让读者感觉，这份摘要是你直接阅读了全文后撰写的。
2. 不要对要点进行简单的罗列或堆砌。你的核心任务是【整合】与【重构】。
3. 输出格式应为一篇格式化良好、适合人类阅读的完整文章。
"""

# --- 辅助函数 ---
def _extract_api_error_message(response):
    try:
        error_detail = response.json()
        api_err_msg = error_detail.get('error', {}).get('message') or error_detail.get('message') or error_detail.get('detail')
        if api_err_msg: return str(api_err_msg)
        return response.text[:200]
    except ValueError:
        return response.text[:200]

def _split_text_intelligently(text, chunk_size=CHUNK_TARGET_SIZE):
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
            if pos > best_split_pos: best_split_pos = pos
        if best_split_pos != -1:
            chunks.append(text[start_index : best_split_pos + 1])
            start_index = best_split_pos + 1
        else:
            chunks.append(text[start_index:end_index])
            start_index = end_index
    return [c for c in chunks if c.strip()]

def _get_last_sentence(text):
    if not text: return ""
    sentences = re.split(r'(?<=[。？！\n])', text.strip())
    return sentences[-1].strip() if sentences else ""

def _optimize_chunk_with_retry(chunk_data):
    text_chunk = chunk_data['text']
    context_sentence = chunk_data.get('context')
    messages = [{"role": "system", "content": HARDCODED_OPTIMIZATION_PROMPT}]
    if context_sentence:
        user_content = (f"为了保持上下文连贯，这是紧接在当前文本之前的最后一句话：\n---CONTEXT---\n{context_sentence}\n---END CONTEXT---\n\n"
                        f"请仅校准并返回以下这段新的文本，不要在你的回答中重复上面的上下文内容：\n---TEXT TO CALIBRATE---\n{text_chunk}\n---END TEXT---")
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
                if content: return {"status": "success", "content": content}
                else: return {"status": "error", "message": "API返回空内容"}
            error_msg = f"API错误 {response.status_code}: {_extract_api_error_message(response)}"
            if response.status_code in [400, 401, 403, 429]: return {"status": "error", "message": error_msg}
        except requests.exceptions.Timeout: error_msg = "请求超时"
        except requests.exceptions.RequestException as e: error_msg = f"网络连接错误: {type(e).__name__}"
        if attempt == RETRY_ATTEMPTS - 1: return {"status": "error", "message": error_msg}
        time.sleep(2 * (attempt + 1))
    return {"status": "error", "message": "未知错误，已达最大重试次数"}

def _perform_text_optimization(raw_text_to_optimize):
    opt_configured_properly = OPT_API_KEY and OPT_API_URL and OPT_API_URL.startswith(('http://', 'https://')) and OPT_MODEL
    if not opt_configured_properly:
        opt_configured_for_check = OPT_API_KEY or (OPT_API_URL and OPT_API_URL != 'https://api.openai.com/v1/chat/completions') or OPT_MODEL
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
    tasks = [{'text': chunk, 'context': (_get_last_sentence(chunks[i-1]) if i > 0 else None)} for i, chunk in enumerate(chunks)]
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS) as executor:
        processed_results = list(executor.map(_optimize_chunk_with_retry, tasks))
    failed_chunks = [res for res in processed_results if res['status'] == 'error']
    if failed_chunks:
        first_error_message = failed_chunks[0]['message']
        print(f"校准过程中有块处理失败，回退到原始文本。失败原因: {first_error_message}")
        return raw_text_to_optimize, f"校准失败 ({first_error_message})", False
    else:
        full_optimized_text = "".join([res['content'] for res in processed_results])
        print("所有块均已成功校准并合并。")
        return full_optimized_text, "校准成功！", True

def _summarize_chunk_with_retry(text_chunk):
    messages = [{"role": "system", "content": PROMPT_SUMMARY_MAP}, {"role": "user", "content": text_chunk}]
    payload = {'model': OPT_MODEL, 'messages': messages, 'temperature': 0.1}
    headers = {'Authorization': f'Bearer {OPT_API_KEY}', 'Content-Type': 'application/json'}
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.post(OPT_API_URL, headers=headers, json=payload, timeout=300)
            if response.status_code == 200:
                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                if content: return {"status": "success", "content": content}
                else: return {"status": "error", "message": "API为Map阶段返回空内容"}
            error_msg = f"API错误 {response.status_code}: {_extract_api_error_message(response)}"
            if response.status_code in [400, 401, 403, 429]: return {"status": "error", "message": error_msg}
        except requests.exceptions.Timeout: error_msg = "请求超时"
        except requests.exceptions.RequestException as e: error_msg = f"网络连接错误: {type(e).__name__}"
        if attempt == RETRY_ATTEMPTS - 1: return {"status": "error", "message": error_msg}
        time.sleep(2 * (attempt + 1))
    return {"status": "error", "message": "未知错误，已达最大重试次数"}

def _perform_summarization(text_to_summarize):
    print("开始总结任务: Map 阶段 - 并发提取要点...")
    chunks = _split_text_intelligently(text_to_summarize)
    if not chunks: return {"status": "error", "message": "待总结文本为空或分割失败"}
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_WORKERS) as executor:
        map_results = list(executor.map(_summarize_chunk_with_retry, chunks))
    failed_chunks = [res for res in map_results if res['status'] == 'error']
    if failed_chunks:
        first_error = failed_chunks[0]['message']
        return {"status": "error", "message": f"提取要点失败 ({first_error})"}
    print("Map 阶段成功。开始 Reduce 阶段 - 整合生成最终摘要...")
    combined_points = "\n\n".join([res['content'] for res in map_results])
    messages = [{"role": "system", "content": PROMPT_SUMMARY_REDUCE}, {"role": "user", "content": combined_points}]
    payload = {'model': OPT_MODEL, 'messages': messages, 'temperature': 0.2}
    headers = {'Authorization': f'Bearer {OPT_API_KEY}', 'Content-Type': 'application/json'}
    try:
        response = requests.post(OPT_API_URL, headers=headers, json=payload, timeout=300)
        if response.status_code == 200:
            data = response.json()
            final_summary = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            if final_summary: return {"status": "success", "summary": final_summary}
            else: return {"status": "error", "message": "API为Reduce阶段返回空内容"}
        else:
            error_msg = f"API错误 {response.status_code}: {_extract_api_error_message(response)}"
            return {"status": "error", "message": f"整合摘要失败 ({error_msg})"}
    except Exception as e: return {"status": "error", "message": f"处理Reduce阶段时发生未知错误: {str(e)}"}

# =============================================================
# --- Web UI 页面服务路由 ---
# =============================================================
@app.route('/')
def index():
    return render_template('index.html')

# =============================================================
# --- OpenAI 兼容 API 路由 ---
# =============================================================
@app.before_request
def check_openai_auth():
    if request.path.startswith('/v1/'):
        if not API_ACCESS_TOKEN:
            print("警告: API被调用，但环境变量 API_ACCESS_TOKEN 未设置。拒绝访问。")
            return jsonify({"error": {"message": "API access is not configured on the server.", "type": "server_error"}}), 500
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": {"message": "Authorization header is missing or invalid.", "type": "invalid_request_error"}}), 401
        token = auth_header.split(' ')[1]
        if token != API_ACCESS_TOKEN:
            return jsonify({"error": {"message": "Incorrect API key provided.", "type": "invalid_request_error"}}), 401

@app.route('/v1/models', methods=['GET'])
def list_models():
    return jsonify({
        "object": "list",
        "data": [
            { "id": MODEL_CALIBRATE, "object": "model", "created": int(time.time()), "owned_by": "xy2yp" },
            { "id": MODEL_SUMMARIZE, "object": "model", "created": int(time.time()), "owned_by": "xy2yp" },
        ]
    })

@app.route('/v1/audio/transcriptions', methods=['POST'])
def openai_audio_transcriptions():
    if 'file' not in request.files: return jsonify({"error": "No file part in the request"}), 400
    audio_file = request.files['file']
    model_requested = request.form.get('model')
    if not model_requested or model_requested not in [MODEL_CALIBRATE, MODEL_SUMMARIZE]:
        return jsonify({"error": f"Model '{model_requested}' is not supported. Please use '{MODEL_CALIBRATE}' or '{MODEL_SUMMARIZE}'."}), 400

    def generate_response():
        try:
            print(f"API Call: Received request for model '{model_requested}'. Starting S2T...")
            yield " " 
            s2t_files = {'file': (audio_file.filename, audio_file.stream, audio_file.mimetype)}
            s2t_payload = {'model': S2T_MODEL}
            s2t_headers = {'Authorization': f'Bearer {S2T_API_KEY}'}
            s2t_response = requests.post(S2T_API_URL, files=s2t_files, data=s2t_payload, headers=s2t_headers, timeout=300)
            if s2t_response.status_code != 200:
                error_details = _extract_api_error_message(s2t_response)
                raise Exception(f"Upstream S2T service failed with status {s2t_response.status_code}: {error_details}")
            raw_transcription = s2t_response.json().get('text', '').strip()
            if not raw_transcription: raise Exception("Upstream S2T service returned empty text.")
        except Exception as e:
            error_payload = {"error": {"message": str(e), "type": "upstream_error", "code": "s2t_failed"}}
            yield json.dumps(error_payload, ensure_ascii=False)
            return

        print("API Call: S2T completed. Starting text optimization...")
        yield " " 
        calibrated_text, opt_message, is_calibrated = _perform_text_optimization(raw_transcription)
        
        final_response = {}
        if model_requested == MODEL_CALIBRATE:
            final_response["text"] = calibrated_text
            if not is_calibrated:
                final_response["x_warning"] = {"code": "calibration_failed", "message": f"Text optimization failed. Returning raw transcription. Reason: {opt_message}"}
        
        elif model_requested == MODEL_SUMMARIZE:
            if not is_calibrated:
                final_response["text"] = raw_transcription
                final_response["x_warning"] = {"code": "calibration_failed_in_summary_workflow", "message": f"The calibration step failed. Returning the raw, un-calibrated transcription as a fallback. Reason: {opt_message}"}
            else:
                yield " " 
                summary_result = _perform_summarization(calibrated_text)
                if summary_result['status'] == 'success':
                    final_response["text"] = summary_result['summary']
                else:
                    final_response["text"] = calibrated_text
                    final_response["x_warning"] = {"code": "summarization_failed", "message": f"Final summarization step failed. Returning the full calibrated text instead. Reason: {summary_result['message']}"}
        yield json.dumps(final_response, ensure_ascii=False)

    return Response(stream_with_context(generate_response()), mimetype='application/json; charset=utf-8')


# =============================================================
# ---  Web UI 数据接口路由 ---
# =============================================================
@app.route('/api/transcribe', methods=['POST'])
def transcribe_and_optimize_audio():
    audio_file = request.files.get('audio_file')
    if not audio_file: return jsonify({"error": "缺少上传的音频文件"}), 400
    try:
        s2t_files = {'file': (audio_file.filename, audio_file.stream, audio_file.mimetype)}
        s2t_payload = {'model': S2T_MODEL}
        s2t_headers = {'Authorization': f'Bearer {S2T_API_KEY}'}
        s2t_response = requests.post(S2T_API_URL, files=s2t_files, data=s2t_payload, headers=s2t_headers, timeout=300)
        if s2t_response.status_code != 200:
            error_details = _extract_api_error_message(s2t_response)
            return jsonify({"error": f"S2T API 返回错误: {s2t_response.status_code} - {error_details}"}), 500
        raw_transcription = s2t_response.json().get('text', '').strip()
        if not raw_transcription: return jsonify({"error": "S2T 服务未能识别出任何文本。"}), 500
    except requests.exceptions.Timeout: return jsonify({"error": "调用 S2T API 超时"}), 500
    except Exception as e: return jsonify({"error": f"处理 S2T 请求时发生未知错误: {type(e).__name__}"}), 500

    final_transcription, opt_message, is_calibrated = _perform_text_optimization(raw_transcription)
    
    if is_calibrated: final_status_message = f"转录完成，{opt_message}"
    elif "跳过" in opt_message: final_status_message = f"转录完成 ({opt_message.replace('校准已跳过', '校准服务')})" 
    else: final_status_message = f"转录完成，{opt_message.replace('校准失败', '但校准失败')}"
    return jsonify({"status": "success", "transcription": final_transcription, "raw_transcription": raw_transcription, "calibration_message": final_status_message, "is_calibrated": is_calibrated})

@app.route('/api/recalibrate', methods=['POST'])
def recalibrate_text():
    data = request.get_json()
    if not data or 'raw_transcription' not in data: return jsonify({"error": "请求体无效或缺少 raw_transcription 字段"}), 400
    raw_text = data.get('raw_transcription')
    if not isinstance(raw_text, str) or not raw_text.strip(): return jsonify({"error": "需要重新校准的文本不能为空"}), 400
    calibrated_text, calibration_status_msg, calibration_success = _perform_text_optimization(raw_text)
    return jsonify({"status": "success", "transcription": calibrated_text, "calibration_message": calibration_status_msg, "is_calibrated": calibration_success})

@app.route('/api/summarize', methods=['POST'])
def summarize_text():
    data = request.get_json()
    if not data or 'text_to_summarize' not in data: return jsonify({"error": "请求体无效或缺少 'text_to_summarize' 字段"}), 400
    text = data.get('text_to_summarize')
    if not text or not text.strip(): return jsonify({"error": "待总结的文本不能为空"}), 400
    result = _perform_summarization(text)
    if result['status'] == 'success': return jsonify({"summary": result['summary']})
    else: return jsonify({"error": result['message']}), 500

# --- 主程序启动入口 ---
if __name__ == '__main__':
    # 启动时进行配置检查
    print("--- S2T 配置检查 ---")
    if not S2T_API_KEY: print("警告: 环境变量 S2T_API_KEY 未设置。")
    if not S2T_API_URL.startswith(('http://', 'https://')): print(f"警告: 环境变量 S2T_API_URL 格式不正确: {S2T_API_URL}。")
    
    print("\n--- OPT 配置检查 ---")
    opt_configured_for_check = OPT_API_KEY or (OPT_API_URL and OPT_API_URL != 'https://api.openai.com/v1/chat/completions') or OPT_MODEL
    if opt_configured_for_check:
        if not OPT_API_KEY: print("警告: 环境变量 OPT_API_KEY 未设置。文本优化功能将无法使用。")
        if OPT_API_KEY and (not OPT_API_URL or not OPT_API_URL.startswith(('http://', 'https://'))): print(f"警告: 环境变量 OPT_API_URL ({OPT_API_URL}) 无效或格式不正确。")
        if OPT_API_KEY and not OPT_MODEL: print("警告: 已设置 OPT_API_KEY 但未设置 OPT_MODEL。")
    else:
        print("提示: OPT服务未配置，校准和总结功能将不可用。")

    print("\n--- API 封装功能检查 ---")
    if not API_ACCESS_TOKEN:
        print("警告: 环境变量 API_ACCESS_TOKEN 未设置或为空。API封装功能将无法通过认证。")
    else:
        print("API封装功能已启用。")
    
    print("\n--------------------\n")
    print(f"服务器正在启动，监听 http://0.0.0.0:5000")
    serve(app, host='0.0.0.0', port=5000)
