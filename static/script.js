document.addEventListener('DOMContentLoaded', function() {
    const audioFileInput = document.getElementById('audioFile');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    const submitBtn = document.getElementById('submitBtn');
    const statusMessage = document.getElementById('statusMessage');
    const transcriptionResult = document.getElementById('transcriptionResult');
    const copyBtn = document.getElementById('copyBtn');
    const recalibrateBtn = document.getElementById('recalibrateBtn');

    let currentRawTranscription = null;

    function updateStatus(message, type) {
        statusMessage.textContent = message || '';
        statusMessage.classList.remove('error', 'success', 'info', 'hidden');
        if (type) {
            statusMessage.classList.add(type);
        } else {
            statusMessage.classList.add('hidden');
        }
        if (message && type) {
            statusMessage.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
    
    function setActionButtonsDisabledState(disabled) {
        submitBtn.disabled = disabled;
        recalibrateBtn.disabled = disabled;
        
        // 复制按钮的禁用状态：如果文本框为空，则始终禁用；否则根据操作状态(disabled参数)决定
        if (transcriptionResult.textContent.trim() === '') {
            copyBtn.disabled = true;
        } else {
            copyBtn.disabled = disabled;
        }
    }

    function resetUIForNewFile() {
        updateStatus(null, null);
        transcriptionResult.textContent = '';
        // copyBtn 不再需要 classList.add('hidden');
        copyBtn.classList.remove('copied-success', 'copied-error');
        copyBtn.textContent = '复制文本';
        currentRawTranscription = null;
        setActionButtonsDisabledState(false); // 重置时会根据文本框内容更新复制按钮禁用状态

        const submitBtnSpan = submitBtn.querySelector('span');
        if (submitBtnSpan) {
            submitBtnSpan.textContent = '开始转录';
        } else {
            submitBtn.textContent = '开始转录';
        }
        const recalibrateBtnSpan = recalibrateBtn.querySelector('span'); // Assuming recalibrate button might also have a span
        if (recalibrateBtnSpan) {
             recalibrateBtnSpan.textContent = '重新校准';
        } else {
             recalibrateBtn.textContent = '重新校准';
        }
    }

    audioFileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            fileNameDisplay.textContent = file.name;
        } else {
            fileNameDisplay.textContent = '未选择文件';
        }
        resetUIForNewFile();
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
        transcriptionResult.textContent = ''; // 清空是为了在 finally 中 setActionButtonsDisabledState 能正确判断 copyBtn 状态
        currentRawTranscription = null;
        // copyBtn 不再需要 classList.add('hidden');

        setActionButtonsDisabledState(true);
        const submitBtnSpan = submitBtn.querySelector('span');
        const originalSubmitBtnText = submitBtnSpan ? submitBtnSpan.textContent : submitBtn.textContent;
        if(submitBtnSpan) submitBtnSpan.textContent = '处理中...'; else submitBtn.textContent = '处理中...';

        try {
            const response = await fetch('/transcribe', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                let errorMsg = `请求失败 (状态 ${response.status})`;
                try { 
                    const errorData = await response.json(); 
                    errorMsg = errorData.error || errorMsg; 
                } catch (e) { 
                    const textError = await response.text(); 
                    errorMsg = textError || errorMsg; 
                    if (response.status === 0 && !textError && errorMsg === `请求失败 (状态 ${response.status})`) {
                        errorMsg = "无法连接到服务器，请检查网络或服务是否在线。";
                    }
                }
                throw new Error(errorMsg);
            }

            const data = await response.json();

            if (data.status === "success" && data.transcription !== undefined) {
                currentRawTranscription = data.raw_transcription;
                const messageType = data.is_calibrated ? 'success' : 'info';
                updateStatus(data.calibration_message || '处理完成。', messageType);
                transcriptionResult.textContent = data.transcription;
                // copyBtn 不再需要 classList.remove('hidden');
                // setActionButtonsDisabledState(false) 在 finally 中会处理 copyBtn 的启用/禁用
            } else if (data.error) {
                 updateStatus(`处理失败: ${data.error}`, 'error');
            } else {
                updateStatus('转录失败或返回结果格式不正确。', 'error');
            }
        } catch (error) {
            console.error('转录错误:', error);
            updateStatus(`发生错误: ${error.message}`, 'error');
        } finally {
            setActionButtonsDisabledState(false); // 根据最终文本框内容决定 copyBtn 状态
            if(submitBtnSpan) submitBtnSpan.textContent = originalSubmitBtnText; else submitBtn.textContent = originalSubmitBtnText;
        }
    });

    recalibrateBtn.addEventListener('click', async function() {
        if (!currentRawTranscription) {
            updateStatus('没有可供重新校准的原始转录文本。请先进行一次完整转录。', 'info');
            return;
        }
        if (currentRawTranscription.trim() === '') {
            updateStatus('原始转录文本为空，无法重新校准。', 'info');
            return;
        }

        updateStatus('正在重新校准...', 'info');
        // copyBtn 不再需要 classList.add('hidden');
        // transcriptionResult.textContent = ''; // 清空放后面，如果失败则不应清空旧的成功结果

        setActionButtonsDisabledState(true);
        const recalibrateBtnSpan = recalibrateBtn.querySelector('span');
        const originalRecalibrateBtnText = recalibrateBtnSpan ? recalibrateBtnSpan.textContent : recalibrateBtn.textContent;
        if(recalibrateBtnSpan) recalibrateBtnSpan.textContent = '校准中...'; else recalibrateBtn.textContent = '校准中...';

        try {
            const response = await fetch('/recalibrate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ raw_transcription: currentRawTranscription })
            });

            if (!response.ok) {
                let errorMsg = `请求失败 (状态 ${response.status})`;
                try { 
                    const errorData = await response.json(); 
                    errorMsg = errorData.error || errorData.message || errorMsg; 
                } catch (e) { 
                    const textError = await response.text(); 
                    errorMsg = textError || errorMsg; 
                    if (response.status === 0 && !textError && errorMsg === `请求失败 (状态 ${response.status})`) {
                        errorMsg = "无法连接到服务器，请检查网络或服务是否在线。";
                    }
                }
                throw new Error(errorMsg);
            }

            const data = await response.json();

            if (data.status === "success" && data.transcription !== undefined && data.calibration_message) {
                const messageType = data.is_calibrated ? 'success' : 'error'; // 如果重新校准失败，用 error 提示
                updateStatus(data.calibration_message, messageType);
                transcriptionResult.textContent = data.transcription; // 更新文本
                // copyBtn 不再需要 classList.remove('hidden');
            } else if (data.error) {
                 updateStatus(`重新校准失败: ${data.error}`, 'error');
            } else {
                updateStatus('重新校准失败或返回结果格式不正确。', 'error');
            }

        } catch (error) {
            console.error('重新校准错误:', error);
            updateStatus(`重新校准时发生错误: ${error.message}`, 'error');
        } finally {
            setActionButtonsDisabledState(false); // 根据最终文本框内容决定 copyBtn 状态
            if(recalibrateBtnSpan) recalibrateBtnSpan.textContent = originalRecalibrateBtnText; else recalibrateBtn.textContent = originalRecalibrateBtnText;
        }
    });

    copyBtn.addEventListener('click', function() {
        if (copyBtn.disabled) return;

        const textToCopy = transcriptionResult.textContent;
        const originalBtnText = copyBtn.textContent; // 固定的 "复制文本"
        copyBtn.classList.remove('copied-success', 'copied-error');

        if (!textToCopy || textToCopy.trim() === '') {
            updateStatus('没有可复制的文本。', 'info'); // 此时按钮应已禁用
            return;
        }

        navigator.clipboard.writeText(textToCopy).then(function() {
            copyBtn.textContent = '已复制!';
            copyBtn.classList.add('copied-success');
            setTimeout(function() {
                copyBtn.textContent = '复制文本'; // 恢复固定文本
                copyBtn.classList.remove('copied-success');
            }, 2000);
        }).catch(function(err) {
            console.error('无法复制文本: ', err);
            copyBtn.textContent = '复制失败';
            copyBtn.classList.add('copied-error');
            setTimeout(function() {
                copyBtn.textContent = '复制文本'; // 恢复固定文本
                copyBtn.classList.remove('copied-error');
            }, 3000);
        });
    });
});
