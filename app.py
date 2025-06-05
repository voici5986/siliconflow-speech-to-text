from flask import Flask, render_template, request, jsonify
import requests
import os

app = Flask(__name__)

# --- S2T (Speech-to-Text) 配置 ---
# 硅基流动或其他兼容 Whisper 的 API
S2T_API_URL = os.environ.get('S2T_API_URL', 'https://api.siliconflow.cn/v1/audio/transcriptions')
S2T_API_KEY = os.environ.get('S2T_API_KEY') # S2T API Key 必须通过环境变量设置
S2T_MODEL = os.environ.get('S2T_MODEL', 'FunAudioLLM/SenseVoiceSmall') # S2T 模型名称

# --- OPT (Optimize Text) 配置 ---
# OpenAI 或兼容 OpenAI API 的服务 (例如：其他国内服务、自部署模型等)
OPT_API_URL = os.environ.get('OPT_API_URL', 'https://api.openai.com/v1/chat/completions') # 默认使用 OpenAI 官方端点
OPT_API_KEY = os.environ.get('OPT_API_KEY') # OPT API Key 必须通过环境变量设置
OPT_MODEL = os.environ.get('OPT_MODEL') # OPT 模型名称 (选择一个适合文本处理的LLM)。注意：这里移除了默认值，如果OPT_API_KEY设置了，OPT_MODEL最好也明确设置。

# *** 硬编码您的优化提示词 (用于 OPT 步骤) ***
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

# 在应用启动时进行一次基本的配置验证 
if not S2T_API_KEY:
    print("警告: 环境变量 S2T_API_KEY 未设置。音频转录功能将无法使用。")
if not S2T_API_URL.startswith(('http://', 'https://')):
     print(f"警告: 环境变量 S2T_API_URL 格式不正确: {S2T_API_URL}。音频转录功能可能无法使用。")

# OPT API 是可选的，但如果设置了，则需要 key 和 endpoint
# 注意：这里修正了变量名 OPT_MODEL_NAME -> OPT_MODEL
if OPT_API_KEY or OPT_API_URL != 'https://api.openai.com/v1/chat/completions' or OPT_MODEL is not None: # 检查OPT_MODEL是否被设置
    print("\n--- OPT 配置检查 ---")
    if not OPT_API_KEY:
        print("警告: 环境变量 OPT_API_KEY 未设置。文本优化功能将无法使用，仅返回原始转录结果。")
    # 注意：这里修正了变量名 OPT_API_ENDPOINT_URL -> OPT_API_URL
    if OPT_API_KEY and not OPT_API_URL.startswith(('http://', 'https://')): # 只在设置了key时才检查URL格式
        print(f"警告: 环境变量 OPT_API_URL 格式不正确: {OPT_API_URL}。文本优化功能可能无法使用。")
    if OPT_API_KEY and not OPT_MODEL: # 只在设置了key时才检查model
         print("警告: 已设置 OPT_API_KEY 但未设置 OPT_MODEL。文本优化功能可能无法按预期工作。")
    print("--------------------\n")


@app.route('/')
def index():
    # 前端页面不再需要输入 prompt
    return render_template('index.html')

@app.route('/transcribe', methods=['POST'])
def transcribe_and_optimize_audio():
    audio_file = request.files.get('audio_file')

    if not audio_file:
        return jsonify({"status": "error", "message": "缺少上传的音频文件"}), 400

    # --- Step 1: 调用 S2T API 进行音频转录 ---
    print("开始调用 S2T API 进行转录...")
    if not S2T_API_KEY:
         return jsonify({"status": "error", "message": "服务器配置错误：缺少 S2T API Key (请设置环境变量 S2T_API_KEY)"}), 500
    if not S2T_API_URL.startswith(('http://', 'https://')):
        return jsonify({"status": "error", "message": f"服务器配置错误：S2T API 端点 URL 格式不正确: {S2T_API_URL}"}), 500

    raw_transcription = ""
    try:
        s2t_files = {
            'file': (audio_file.filename, audio_file.stream, audio_file.mimetype)
        }
        s2t_payload = {
            'model': S2T_MODEL,
        }
        s2t_headers = {
            'Authorization': f'Bearer {S2T_API_KEY}'
        }

        s2t_response = requests.post(S2T_API_URL, files=s2t_files, data=s2t_payload, headers=s2t_headers)

        if s2t_response.status_code == 200:
            try:
                s2t_data = s2t_response.json()
                if 'text' in s2t_data:
                    raw_transcription = s2t_data['text']
                    print(f"S2T 转录成功，原始文本长度: {len(raw_transcription)}")
                    print(f"原始文本片段: {raw_transcription[:200]}...")
                else:
                    print(f"S2T API 响应缺少 'text' 字段: {s2t_data}")
                    return jsonify({"status": "error", "message": "S2T API 响应中缺少转录文本"}), 500
            except ValueError:
                 print(f"无法解析 S2T API 响应为 JSON: {s2t_response.text}")
                 return jsonify({"status": "error", "message": f"无法解析 S2T API 响应为 JSON: {s2t_response.text}"}), 500
        else:
            s2t_error_message = f"S2T API 返回错误: {s2t_response.status_code}."
            try:
                s2t_error_detail = s2t_response.json()
                if isinstance(s2t_error_detail, dict) and ('message' in s2t_error_detail or 'detail' in s2t_error_detail):
                    s2t_error_message += f" 详情: {s2t_error_detail.get('message') or s2t_error_detail.get('detail')}"
                else:
                     s2t_error_message += f" 响应内容: {s2t_response.text}"
            except ValueError:
                s2t_error_message += f" 响应内容: {s2t_response.text}"
            print(s2t_error_message)
            return jsonify({"status": "error", "message": s2t_error_message}), s2t_response.status_code

    except requests.exceptions.RequestException as e:
        print(f"调用 S2T API 时发生连接错误: {str(e)}")
        return jsonify({"status": "error", "message": f"调用 S2T API 时发生连接错误: {str(e)}"}), 500
    except Exception as e:
        print(f"处理 S2T 请求时发生未知错误: {e}")
        return jsonify({"status": "error", "message": "处理 S2T 请求时发生未知错误。"}), 500

    # 如果 S2T 成功获取了文本，则进行 Step 2
    optimized_transcription = raw_transcription # 默认使用原始转录结果
    print("S2T 转录成功，准备进行文本优化...")

    # --- Step 2: 调用 OPT API 进行文本优化 ---
    # 检查 OPT 配置是否完整 (需要 Key, URL, Model)，只有完整时才调用 OPT API
    if OPT_API_KEY and OPT_API_URL.startswith(('http://', 'https://')) and OPT_MODEL:
        print("开始调用 OPT API 进行文本优化...")
        try:
            opt_headers = {
                'Authorization': f'Bearer {OPT_API_KEY}',
                'Content-Type': 'application/json'
            }
            # 构建 OpenAI 兼容的聊天请求体
            opt_payload = {
                'model': OPT_MODEL,
                'messages': [
                    {"role": "system", "content": HARDCODED_OPTIMIZATION_PROMPT},
                    {"role": "user", "content": raw_transcription}
                ],
                # 您可以根据需要添加其他参数，例如 temperature, top_p 等
                'temperature': 0.1 # 较低的温度有助于保持忠实原文
            }

            opt_response = requests.post(OPT_API_URL, headers=opt_headers, json=opt_payload)

            if opt_response.status_code == 200:
                try:
                    opt_data = opt_response.json()
                    # 提取聊天模型的回复内容
                    if opt_data and 'choices' in opt_data and len(opt_data['choices']) > 0 and 'message' in opt_data['choices'][0] and 'content' in opt_data['choices'][0]['message']:
                         optimized_transcription = opt_data['choices'][0]['message']['content']
                         print(f"OPT 文本优化成功，优化后文本长度: {len(optimized_transcription)}")
                         print(f"优化后文本片段: {optimized_transcription[:200]}...")
                    else:
                        print(f"OPT API 响应格式不正确或缺少内容: {opt_data}")
                        # 如果 OPT API 调用成功但响应格式不对，我们仍然返回原始转录结果
                        print("OPT 响应格式错误，返回原始转录结果。")
                except ValueError:
                    print(f"无法解析 OPT API 响应为 JSON: {opt_response.text}")
                    # 如果 OPT API 调用成功但无法解析 JSON，我们仍然返回原始转录结果
                    print("OPT 响应 JSON 解析错误，返回原始转录结果。")
            else:
                opt_error_message = f"OPT API 返回错误: {opt_response.status_code}."
                try:
                    opt_error_detail = opt_response.json()
                    if isinstance(opt_error_detail, dict) and ('message' in opt_error_detail or 'detail' in opt_error_detail):
                        opt_error_message += f" 详情: {opt_error_detail.get('message') or opt_error_detail.get('detail')}"
                    else:
                         opt_error_message += f" 响应内容: {opt_response.text}"
                except ValueError:
                    opt_error_message += f" 响应内容: {opt_response.text}"
                print(opt_error_message)
                # 如果 OPT API 调用失败，我们仍然返回原始转录结果
                print("OPT API 调用失败，返回原始转录结果。")

        except requests.exceptions.RequestException as e:
            print(f"调用 OPT API 时发生连接错误: {str(e)}")
            # 如果 OPT API 调用发生连接错误，我们仍然返回原始转录结果
            print("调用 OPT API 时发生连接错误，返回原始转录结果。")
        except Exception as e:
            print(f"处理 OPT 请求时发生未知错误: {e}")
            # 如果处理 OPT 请求时发生未知错误，我们仍然返回原始转录结果
            print("处理 OPT 请求时发生未知错误，返回原始转录结果。")
    else:
        # 打印更详细的跳过原因
        skip_reason = []
        if not OPT_API_KEY:
            skip_reason.append("缺少 OPT_API_KEY")
        if not OPT_API_URL or not OPT_API_URL.startswith(('http://', 'https://')):
             skip_reason.append("OPT_API_URL 无效或格式不正确")
        if not OPT_MODEL:
             skip_reason.append("缺少 OPT_MODEL")
        print(f"OPT API 配置不完整 ({', '.join(skip_reason)})，跳过文本优化步骤，返回原始转录结果。")


    # --- Step 3: 返回最终结果 ---
    # 无论 OPT 是否成功，都返回一个结果。如果 OPT 失败或未配置，返回原始转录。
    return jsonify({"status": "success", "transcription": optimized_transcription})

if __name__ == '__main__':
    # 在生产环境中，不要使用 debug=True
    app.run(debug=True)
