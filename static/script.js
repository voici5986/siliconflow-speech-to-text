document.addEventListener('DOMContentLoaded', () => {
    const transcriptionForm = document.getElementById('transcriptionForm');
    const submitBtn = document.getElementById('submitBtn');
    const audioFileIn = document.getElementById('audioFile');
    // 移除了对 apiEndpointIn, apiKeyIn, modelNameIn 的引用
    const transcriptionResultEl = document.getElementById('transcriptionResult');
    const statusMessageEl = document.getElementById('statusMessage');
    const copyBtn = document.getElementById('copyBtn');

    // 添加复制按钮点击事件
    copyBtn.addEventListener('click', async () => {
        const textToCopy = transcriptionResultEl.textContent;
        try {
            await navigator.clipboard.writeText(textToCopy);
            const originalText = copyBtn.textContent;
            copyBtn.textContent = '已复制！';
            copyBtn.classList.add('bg-green-500');
            setTimeout(() => {
                copyBtn.textContent = originalText;
                copyBtn.classList.remove('bg-green-500');
            }, 2000);
        } catch (err) {
            console.error('复制失败:', err);
            copyBtn.textContent = '复制失败';
            copyBtn.classList.add('bg-red-500');
            setTimeout(() => {
                copyBtn.textContent = '复制文本';
                copyBtn.classList.remove('bg-red-500');
            }, 2000);
        }
    });

    // 移除了保存和加载表单数据的函数 (saveFormData, loadFormData)
    // 移除了加载表单数据的调用 (loadFormData())
    // 移除了保存表单数据的事件监听器 (apiEndpointIn, apiKeyIn, modelNameIn 的 input 事件)

    submitBtn.addEventListener('click', async (event) => {
        event.preventDefault();

        statusMessageEl.textContent = '';
        statusMessageEl.className = 'status-message'; // Reset classes
        transcriptionResultEl.textContent = '';
        copyBtn.classList.add('hidden'); // 隐藏复制按钮

        const audioFile = audioFileIn.files[0];
        // 移除了获取 apiEndpointUrl, apiKey, modelName 的代码

        if (!audioFile) {
            statusMessageEl.textContent = '请选择一个音频文件。';
            statusMessageEl.classList.add('error');
            return;
        }
        // 移除了对 apiEndpointUrl, apiKey, modelName 的空值验证

        const formData = new FormData();
        formData.append('audio_file', audioFile);
        // 移除了将 apiEndpointUrl, apiKey, modelName 添加到 formData 的代码

        statusMessageEl.textContent = '正在处理中，请稍候...';
        statusMessageEl.classList.add('info');
        submitBtn.disabled = true;
        submitBtn.textContent = '处理中...';
        // 添加一个类来改变按钮样式，例如 bg-gray-400
        submitBtn.classList.remove('bg-indigo-600', 'hover:bg-indigo-700'); // 移除原有颜色类
        submitBtn.classList.add('bg-gray-400', 'cursor-not-allowed'); // 添加禁用样式类


        try {
            // 发送请求到后端的 /transcribe 端点
            const response = await fetch('/transcribe', {
                method: 'POST',
                body: formData // 只发送音频文件
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                transcriptionResultEl.textContent = result.transcription;
                statusMessageEl.textContent = '转录成功！';
                statusMessageEl.className = 'status-message success'; // Update classes
                copyBtn.classList.remove('hidden'); // 显示复制按钮
            } else {
                transcriptionResultEl.textContent = '';
                // 显示后端返回的错误信息
                statusMessageEl.textContent = `错误: ${result.message || '未知错误'}`;
                statusMessageEl.className = 'status-message error'; // Update classes
            }

        } catch (error) {
            console.error('Fetch error:', error);
            transcriptionResultEl.textContent = '';
            statusMessageEl.textContent = '请求失败，请检查网络连接或联系管理员。';
            statusMessageEl.className = 'status-message error'; // Update classes
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = '开始转录';
            // 恢复按钮样式
            submitBtn.classList.remove('bg-gray-400', 'cursor-not-allowed');

        }
    });
});
