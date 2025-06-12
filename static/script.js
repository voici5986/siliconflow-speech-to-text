document.addEventListener('DOMContentLoaded', function() {
    // --- 元素获取 ---
    const audioFileInput = document.getElementById('audioFile');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    const submitBtn = document.getElementById('submitBtn');
    const statusMessage = document.getElementById('statusMessage');
    const transcriptionResult = document.getElementById('transcriptionResult');
    const copyBtn = document.getElementById('copyBtn');
    const recalibrateBtn = document.getElementById('recalibrateBtn');
    const summarizeBtn = document.getElementById('summarizeBtn');

    // --- 状态变量 ---
    let currentRawTranscription = null;
    let currentCalibratedText = null;
    let summaryText = null;
    let isShowingSummary = false;

    // --- UI 更新函数 ---
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
        // 主提交按钮是独立的
        submitBtn.disabled = disabled;
        
        // 结果区域的操作按钮
        const hasContent = currentCalibratedText && currentCalibratedText.trim() !== '';
        recalibrateBtn.disabled = disabled || !hasContent;
        copyBtn.disabled = disabled || transcriptionResult.textContent.trim() === '';
        summarizeBtn.disabled = disabled || !hasContent;
    }

    // --- 状态重置函数 ---
    function resetSummaryState() {
        summaryText = null;
        isShowingSummary = false;
        summarizeBtn.textContent = '量子速读';
        if (currentCalibratedText) {
            transcriptionResult.textContent = currentCalibratedText;
        } else {
            transcriptionResult.textContent = '';
        }
    }

    // --- 事件监听器 ---
    audioFileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            // 1. 更新文件名 (保留)
            fileNameDisplay.textContent = file.name;
            
            // 2. 清理上一次的转录结果和状态，为新任务做准备
            updateStatus(null, null);
            currentRawTranscription = null;
            currentCalibratedText = null;
            resetSummaryState(); // 重置摘要状态，这也会清空文本框
    
            // 3. 启用提交按钮，禁用其他操作按钮
            submitBtn.disabled = false;
            recalibrateBtn.disabled = true;
            copyBtn.disabled = true;
            summarizeBtn.disabled = true;
            copyBtn.textContent = '复制文本'; // 确保复制按钮文本也被重置
            copyBtn.classList.remove('copied-success', 'copied-error');

        } else {
            // 如果用户取消了文件选择
            fileNameDisplay.textContent = '未选择文件';
            submitBtn.disabled = true;
        }
    });
    
    function handleSuccess(data, operationType) {
        if (data.raw_transcription) {
            currentRawTranscription = data.raw_transcription;
        }
        currentCalibratedText = data.transcription;
        
        const messageType = data.is_calibrated ? 'success' : 'info';
        updateStatus(data.calibration_message || `${operationType}完成。`, messageType);
        transcriptionResult.textContent = data.transcription;
        
        resetSummaryState();
    }

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
        setActionButtonsDisabledState(true);
        
        const submitBtnSpan = submitBtn.querySelector('span') || submitBtn;
        const originalText = submitBtnSpan.textContent;
        submitBtnSpan.textContent = '处理中...';

        try {
            const response = await fetch('/api/transcribe', { method: 'POST', body: formData });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `请求失败 (状态 ${response.status})` }));
                throw new Error(errorData.error);
            }
            const data = await response.json();
            if (data.status === "success") {
                handleSuccess(data, "转录");
            } else {
                throw new Error(data.error || '转录失败或返回结果格式不正确。');
            }
        } catch (error) {
            console.error('转录错误:', error);
            updateStatus(`发生错误: ${error.message}`, 'error');
            currentCalibratedText = null;
        } finally {
            setActionButtonsDisabledState(false);
            submitBtnSpan.textContent = originalText;
        }
    });

    recalibrateBtn.addEventListener('click', async function() {
        if (!currentRawTranscription) {
            updateStatus('没有可供重新校准的原始转录文本。', 'info');
            return;
        }
        
        updateStatus('正在重新校准...', 'info');
        setActionButtonsDisabledState(true);
        const originalText = recalibrateBtn.textContent;
        recalibrateBtn.textContent = '校准中...';

        try {
            const response = await fetch('/api/recalibrate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ raw_transcription: currentRawTranscription })
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `请求失败 (状态 ${response.status})` }));
                throw new Error(errorData.error);
            }
            const data = await response.json();
            if (data.status === "success") {
                handleSuccess(data, "重新校准");
            } else {
                throw new Error(data.error || '重新校准失败或返回结果格式不正确。');
            }
        } catch (error) {
            console.error('重新校准错误:', error);
            updateStatus(`重新校准时发生错误: ${error.message}`, 'error');
        } finally {
            setActionButtonsDisabledState(false);
            recalibrateBtn.textContent = originalText;
        }
    });
    
    summarizeBtn.addEventListener('click', async function() {
        // 情况1：切换视图
        if (summaryText) {
            isShowingSummary = !isShowingSummary;
            if (isShowingSummary) {
                transcriptionResult.textContent = summaryText;
                summarizeBtn.textContent = '显示原文';
            } else {
                transcriptionResult.textContent = currentCalibratedText;
                summarizeBtn.textContent = '显示摘要';
            }
            // 切换视图后，需要重新评估复制按钮的状态
            copyBtn.disabled = transcriptionResult.textContent.trim() === '';
            return;
        }

        // 情况2：首次生成摘要
        if (!currentCalibratedText || currentCalibratedText.trim() === '') {
            updateStatus('没有可供总结的文本。', 'info');
            return;
        }

        updateStatus('正在生成摘要...', 'info');
        setActionButtonsDisabledState(true);
        const originalText = summarizeBtn.textContent;
        summarizeBtn.textContent = '生成中...';

        try {
            const response = await fetch('/api/summarize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text_to_summarize: currentCalibratedText })
            });
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `请求失败 (状态 ${response.status})` }));
                throw new Error(errorData.error);
            }

            const data = await response.json();
            if (data.summary) {
                summaryText = data.summary;
                isShowingSummary = true;
                
                transcriptionResult.textContent = summaryText;
                updateStatus('摘要生成成功！', 'success');
                summarizeBtn.textContent = '显示原文';
            } else {
                throw new Error('API未能返回有效的摘要内容。');
            }

        } catch (error) {
            console.error('生成摘要错误:', error);
            updateStatus(`生成摘要失败 (${error.message})，请重试...`, 'error');
            summarizeBtn.textContent = originalText;
        } finally {
            setActionButtonsDisabledState(false);
        }
    });

    copyBtn.addEventListener('click', function() {
        if (copyBtn.disabled) return;

        const textToCopy = transcriptionResult.textContent;
        const originalBtnText = "复制文本";
        copyBtn.classList.remove('copied-success', 'copied-error');

        if (!textToCopy || textToCopy.trim() === '') {
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
