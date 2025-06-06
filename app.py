from flask import Flask, render_template, request, jsonify
import requests
import os

app = Flask(__name__)

# --- S2T (Speech-to-Text) 配置 ---
S2T_API_URL = os.environ.get('S2T_API_URL', 'https://api.siliconflow.cn/v1/audio/transcriptions')
S2T_API_KEY = os.environ.get('S2T_API_KEY')
S2T_MODEL = os.environ.get('S2T_MODEL', 'FunAudioLLM/SenseVoiceSmall')

# --- OPT (Optimize Text) 配置 ---
OPT_API_URL = os.environ.get('OPT_API_URL', 'https://api.openai.com/v1/chat/completions')
OPT_API_KEY = os.environ.get('OPT_API_KEY')
OPT_MODEL = os.environ.get('OPT_MODEL')

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

if not S2T_API_KEY:
    print("警告: 环境变量 S2T_API_KEY 未设置。音频转录功能将无法使用。")
if not S2T_API_URL.startswith(('http://', 'https://')):
     print(f"警告: 环境变量 S2T_API_URL 格式不正确: {S2T_API_URL}。音频转录功能可能无法使用。")

if OPT_API_KEY or OPT_API_URL != 'https://api.openai.com/v1/chat/completions' or OPT_MODEL is not None:
    print("\n--- OPT 配置检查 ---")
    if not OPT_API_KEY:
        print("警告: 环境变量 OPT_API_KEY 未设置。文本优化功能将无法使用，仅返回原始转录结果。")
    if OPT_API_KEY and not OPT_API_URL.startswith(('http://', 'https://')):
        print(f"警告: 环境变量 OPT_API_URL 格式不正确: {OPT_API_URL}。文本优化功能可能无法使用。")
    if OPT_API_KEY and not OPT_MODEL:
         print("警告: 已设置 OPT_API_KEY 但未设置 OPT_MODEL。文本优化功能可能无法按预期工作。")
    print("--------------------\n")


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/transcribe', methods=['POST'])
def transcribe_and_optimize_audio():
    audio_file = request.files.get('audio_file')

    if not audio_file:
        # 前端JS会处理错误提示，这里返回结构化的error
        return jsonify({"error": "缺少上传的音频文件"}), 400

    # --- Step 1: 调用 S2T API 进行音频转录 ---
    print("开始调用 S2T API 进行转录...")
    if not S2T_API_KEY:
         return jsonify({"error": "服务器配置错误：缺少 S2T API Key"}), 500 # 简化错误信息
    if not S2T_API_URL.startswith(('http://', 'https://')):
        return jsonify({"error": f"服务器配置错误：S2T API 端点 URL 格式不正确"}), 500 # 简化错误信息

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
        s2t_response = requests.post(S2T_API_URL, files=s2t_files, data=s2t_payload, headers=s2t_headers, timeout=300) # 增加超时

        if s2t_response.status_code == 200:
            try:
                s2t_data = s2t_response.json()
                if 'text' in s2t_data:
                    raw_transcription = s2t_data['text']
                    print(f"S2T 转录成功，原始文本长度: {len(raw_transcription)}")
                else:
                    print(f"S2T API 响应缺少 'text' 字段: {s2t_data}")
                    return jsonify({"error": "S2T API 响应中缺少转录文本"}), 500
            except ValueError:
                 print(f"无法解析 S2T API 响应为 JSON: {s2t_response.text}")
                 return jsonify({"error": f"无法解析 S2T API 响应"}), 500 # 简化错误信息
        else:
            s2t_error_message = f"S2T API 返回错误: {s2t_response.status_code}."
            try:
                s2t_error_detail = s2t_response.json()
                # 尝试获取更具体的错误信息
                api_err_msg = s2t_error_detail.get('error', {}).get('message') or \
                              s2t_error_detail.get('message') or \
                              s2t_error_detail.get('detail')
                if api_err_msg:
                     s2t_error_message += f" 详情: {api_err_msg}"
                else:
                    s2t_error_message += f" 响应内容: {s2t_response.text[:200]}" # 限制长度
            except ValueError:
                s2t_error_message += f" 响应内容: {s2t_response.text[:200]}" # 限制长度
            print(s2t_error_message)
            return jsonify({"error": s2t_error_message}), s2t_response.status_code

    except requests.exceptions.Timeout:
        print(f"调用 S2T API 时发生超时错误")
        return jsonify({"error": "调用 S2T API 超时，请稍后再试或检查文件大小。"}), 500
    except requests.exceptions.RequestException as e:
        print(f"调用 S2T API 时发生连接错误: {str(e)}")
        return jsonify({"error": f"调用 S2T API 时发生连接错误"}), 500 # 简化错误信息
    except Exception as e:
        print(f"处理 S2T 请求时发生未知错误: {e}")
        return jsonify({"error": "处理 S2T 请求时发生未知错误"}), 500

    optimized_transcription = raw_transcription
    calibration_status_message = "转录完成!" # 默认提示
    is_calibrated_successfully = False # 新增状态变量

    print("S2T 转录成功，准备进行文本优化...")

    # --- Step 2: 调用 OPT API 进行文本优化 ---
    opt_configured_properly = OPT_API_KEY and OPT_API_URL.startswith(('http://', 'https://')) and OPT_MODEL

    if opt_configured_properly:
        print("开始调用 OPT API 进行文本优化...")
        try:
            opt_headers = {
                'Authorization': f'Bearer {OPT_API_KEY}',
                'Content-Type': 'application/json'
            }
            opt_payload = {
                'model': OPT_MODEL,
                'messages': [
                    {"role": "system", "content": HARDCODED_OPTIMIZATION_PROMPT},
                    {"role": "user", "content": raw_transcription}
                ],
                'temperature': 0.1
            }
            opt_response = requests.post(OPT_API_URL, headers=opt_headers, json=opt_payload, timeout=300) # 增加超时

            if opt_response.status_code == 200:
                try:
                    opt_data = opt_response.json()
                    if opt_data and 'choices' in opt_data and len(opt_data['choices']) > 0 and \
                       'message' in opt_data['choices'][0] and 'content' in opt_data['choices'][0]['message']:
                        optimized_transcription = opt_data['choices'][0]['message']['content']
                        calibration_status_message = "转录完成，已校准！" # 修改提示
                        is_calibrated_successfully = True # 设置校准成功
                        print(f"OPT 文本优化成功，优化后文本长度: {len(optimized_transcription)}")
                    else:
                        print(f"OPT API 响应格式不正确或缺少内容: {opt_data}")
                        calibration_status_message = "转录完成，未校准 (校准服务响应格式错误)" # 修改提示
                except ValueError:
                    print(f"无法解析 OPT API 响应为 JSON: {opt_response.text}")
                    calibration_status_message = "转录完成，未校准 (校准服务响应解析错误)" # 修改提示
            else: # OPT API 调用失败
                opt_error_message = f"OPT API 返回错误: {opt_response.status_code}."
                try:
                    opt_error_detail = opt_response.json()
                    api_err_msg = opt_error_detail.get('error', {}).get('message') or \
                                  opt_error_detail.get('message') or \
                                  opt_error_detail.get('detail')
                    if api_err_msg:
                        opt_error_message += f" 详情: {api_err_msg}"
                    else:
                        opt_error_message += f" 响应内容: {opt_response.text[:200]}"
                except ValueError:
                    opt_error_message += f" 响应内容: {opt_response.text[:200]}"
                print(opt_error_message)
                calibration_status_message = f"转录完成，未校准 (校准服务调用失败: {opt_response.status_code})" 

        except requests.exceptions.Timeout:
            print(f"调用 OPT API 时发生超时错误")
            calibration_status_message = "转录完成，未校准 (校准服务超时)"
        except requests.exceptions.RequestException as e:
            print(f"调用 OPT API 时发生连接错误: {str(e)}")
            calibration_status_message = "转录完成，未校准 (无法连接校准服务)"
        except Exception as e:
            print(f"处理 OPT 请求时发生未知错误: {e}")
            calibration_status_message = "转录完成，未校准 (校准时发生未知错误)"
    else: # OPT 配置不完整，跳过优化
        skip_reason_parts = []
        if not OPT_API_KEY: skip_reason_parts.append("缺少API Key")
        if not OPT_API_URL or not OPT_API_URL.startswith(('http://', 'https://')): skip_reason_parts.append("API URL无效")
        if not OPT_MODEL: skip_reason_parts.append("缺少模型名称")
        
        if not skip_reason_parts: # 如果OPT配置完全为空（所有相关环境变量都未设置）
             calibration_status_message = "转录完成 (校准服务未配置)"
        else:
            skip_reason = ", ".join(skip_reason_parts)
            calibration_status_message = f"转录完成，未校准 (校准服务配置不完整: {skip_reason})"
        print(f"OPT API 配置不完整，跳过文本优化步骤。原因: {calibration_status_message}")


    # --- Step 3: 返回最终结果 ---
    # 返回给前端的status字段表示整个请求的成功与否，
    # calibration_message 提供了更详细的关于转录和校准状态的信息
    # is_calibrated 明确指示校准是否成功
    return jsonify({
        "status": "success", # 表示 /transcribe 接口本身调用成功，获取到了转录文本
        "transcription": optimized_transcription,
        "calibration_message": calibration_status_message, # 新增字段，用于前端显示
        "is_calibrated": is_calibrated_successfully # 新增布尔字段
    })


if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000)
