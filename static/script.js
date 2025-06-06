// Ensure the script runs only after the DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    const audioFileInput = document.getElementById('audioFile');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    const submitBtn = document.getElementById('submitBtn');
    const statusMessage = document.getElementById('statusMessage');
    const transcriptionResult = document.getElementById('transcriptionResult');
    const copyBtn = document.getElementById('copyBtn');

    function updateStatus(message, type) {
        statusMessage.textContent = message || '';
        statusMessage.classList.remove('error', 'success', 'info', 'hidden');
        if (type) {
            statusMessage.classList.add(type);
        } else {
            statusMessage.classList.add('hidden');
        }
    }

    audioFileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            fileNameDisplay.textContent = file.name;
        } else {
            fileNameDisplay.textContent = '未选择文件';
        }
        updateStatus(null, null);
        transcriptionResult.textContent = '';
        copyBtn.classList.add('hidden');
        copyBtn.classList.remove('copied-success', 'copied-error');
        copyBtn.textContent = '复制文本';
    });

    submitBtn.addEventListener('click', async function(event) {
        event.preventDefault();
        const file = audioFileInput.files[0];

        if (!file) {
            updateStatus('请先选择一个音频文件。', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('audio_file', file);

        updateStatus('正在上传和转录音频...', 'info');
        transcriptionResult.textContent = '';
        copyBtn.classList.add('hidden');
        copyBtn.classList.remove('copied-success', 'copied-error');
        copyBtn.textContent = '复制文本';

        submitBtn.disabled = true;
        const originalSubmitBtnText = submitBtn.querySelector('span').textContent;
        submitBtn.querySelector('span').textContent = '处理中...';

        try {
            const response = await fetch('/transcribe', {
                method: 'POST',
                body: formData
            });

            // 首先检查响应是否OK，如果不是，则尝试解析错误体
            if (!response.ok) {
                let errorMsg = `请求失败，状态码: ${response.status}`;
                try {
                    const errorData = await response.json();
                    // 后端现在统一返回 {"error": "具体错误信息"}
                    errorMsg = errorData.error || errorMsg;
                } catch (e) {
                    // 如果错误响应体不是JSON或解析失败
                    const textError = await response.text();
                    errorMsg = textError || errorMsg;
                    if (response.status === 0 && !textError) { // 特殊处理网络不通的情况
                        errorMsg = "无法连接到服务器，请检查网络或服务状态。";
                    }
                }
                throw new Error(errorMsg);
            }

            // 如果响应OK，解析JSON数据
            const data = await response.json();

            // 后端返回的 status: "success" 表示获取到了转录文本
            if (data.status === "success" && data.transcription !== undefined) {
                // 使用后端返回的 calibration_message 作为提示
                // 使用 is_calibrated 来决定提示的类型 (success or info/warning)
                const messageType = data.is_calibrated ? 'success' : 'info'; // 如果未校准，用 info 类型
                updateStatus(data.calibration_message || '处理完成。', messageType);
                
                transcriptionResult.textContent = data.transcription;
                copyBtn.classList.remove('hidden');
            } else if (data.error) { // 后端可能在200 OK响应中也返回结构化错误
                 updateStatus(`处理失败: ${data.error}`, 'error');
                 transcriptionResult.textContent = '';
                 copyBtn.classList.add('hidden');
            }
             else {
                // 一般不会走到这里，因为非OK响应已在前面处理
                updateStatus('转录失败或返回结果格式不正确。', 'error');
                transcriptionResult.textContent = '';
                copyBtn.classList.add('hidden');
            }

        } catch (error) {
            console.error('错误:', error);
            // error.message 现在应该包含了后端传来的具体错误信息或fetch的错误
            updateStatus(`发生错误: ${error.message}`, 'error');
            transcriptionResult.textContent = '';
            copyBtn.classList.add('hidden');
        } finally {
            submitBtn.disabled = false;
            submitBtn.querySelector('span').textContent = originalSubmitBtnText;
        }
    });

    copyBtn.addEventListener('click', function() {
        const textToCopy = transcriptionResult.textContent;
        const originalBtnText = copyBtn.textContent;
        copyBtn.classList.remove('copied-success', 'copied-error');

        if (!textToCopy) {
            updateStatus('没有可复制的文本。', 'info');
            return;
        }

        navigator.clipboard.writeText(textToCopy).then(function() {
            copyBtn.textContent = '已复制!';
            copyBtn.classList.add('copied-success');
            setTimeout(function() {
                copyBtn.textContent = originalBtnText;
                copyBtn.classList.remove('copied-success');
            }, 2000);
        }).catch(function(err) {
            console.error('无法复制文本: ', err);
            copyBtn.textContent = '复制失败';
            copyBtn.classList.add('copied-error');
            setTimeout(function() {
                copyBtn.textContent = originalBtnText;
                copyBtn.classList.remove('copied-error');
            }, 3000);
        });
    });
});
