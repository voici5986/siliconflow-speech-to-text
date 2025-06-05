// Ensure the script runs only after the DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Get references to the DOM elements
    const audioFileInput = document.getElementById('audioFile');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    // const transcriptionForm = document.getElementById('transcriptionForm'); // Not directly used, but good to have if needed later
    const submitBtn = document.getElementById('submitBtn');
    const statusMessage = document.getElementById('statusMessage');
    const transcriptionResult = document.getElementById('transcriptionResult');
    const copyBtn = document.getElementById('copyBtn');

    // Helper function to update status messages
    function updateStatus(message, type) {
        statusMessage.textContent = message || ''; // Set message or clear if null/undefined
        // Remove all specific type classes and hidden
        statusMessage.classList.remove('error', 'success', 'info', 'hidden');

        if (type) {
            statusMessage.classList.add(type); // Add 'error', 'success', or 'info'
        } else {
            // If no type, effectively hide the message by adding 'hidden'
            // and ensuring no type class is present.
            statusMessage.classList.add('hidden');
        }
    }

    // --- File Name Display Logic ---
    audioFileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            fileNameDisplay.textContent = file.name;
            // Optional: If fileNameDisplay could have helper classes for truncation/wrapping, manage them here.
            // Our CSS for .file-name-display should handle word wrapping.
        } else {
            fileNameDisplay.textContent = '未选择文件';
        }
        // Reset results/status when a new file is selected
        updateStatus(null, null); // Hide status message
        transcriptionResult.textContent = '';
        copyBtn.classList.add('hidden');
        // Reset copy button appearance if it was in a 'copied' state
        copyBtn.classList.remove('copied-success', 'copied-error');
        copyBtn.textContent = '复制文本'; // Reset button text
    });

    // --- Form Submission Logic ---
    submitBtn.addEventListener('click', async function(event) {
        event.preventDefault(); // Prevent default form submission

        const file = audioFileInput.files[0];

        if (!file) {
            updateStatus('请先选择一个音频文件。', 'error');
            return; // Stop the function execution
        }

        // Prepare form data
        const formData = new FormData();
        formData.append('audio_file', file);

        // Show processing status and disable button
        updateStatus('正在上传和转录音频...', 'info');
        transcriptionResult.textContent = ''; // Clear previous result
        copyBtn.classList.add('hidden'); // Hide copy button
        copyBtn.classList.remove('copied-success', 'copied-error'); // Reset copy button style
        copyBtn.textContent = '复制文本'; // Reset copy button text

        submitBtn.disabled = true;
        const originalSubmitBtnText = submitBtn.querySelector('span').textContent;
        submitBtn.querySelector('span').textContent = '处理中...';

        try {
            // Send the file to the backend
            const response = await fetch('/transcribe', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                let errorMsg = `HTTP error! status: ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorMsg = errorData.error || errorMsg; // Use server's error message if available
                } catch (e) {
                    // If response is not JSON or error parsing JSON
                    const textError = await response.text(); // Try to get text error
                    errorMsg = textError || errorMsg;
                }
                throw new Error(errorMsg);
            }

            const data = await response.json();

            if (data.transcription) {
                updateStatus('转录完成！', 'success'); // Clear message part, only show type
                transcriptionResult.textContent = data.transcription;
                copyBtn.classList.remove('hidden');
            } else {
                updateStatus('转录失败或返回结果为空。', 'error');
                transcriptionResult.textContent = '';
                copyBtn.classList.add('hidden');
            }

        } catch (error) {
            console.error('Error:', error);
            updateStatus(`转录过程中发生错误: ${error.message}`, 'error');
            transcriptionResult.textContent = '';
            copyBtn.classList.add('hidden');
        } finally {
            submitBtn.disabled = false;
            submitBtn.querySelector('span').textContent = originalSubmitBtnText;
        }
    });

    // --- Copy Text Logic ---
    copyBtn.addEventListener('click', function() {
        const textToCopy = transcriptionResult.textContent;
        const originalBtnText = copyBtn.textContent; // Store original or current text

        // Remove previous styling states before attempting to copy
        copyBtn.classList.remove('copied-success', 'copied-error');

        if (!textToCopy) {
            updateStatus('没有可复制的文本。', 'info'); // Or 'error'
            return;
        }

        navigator.clipboard.writeText(textToCopy).then(function() {
            copyBtn.textContent = '已复制!';
            copyBtn.classList.add('copied-success'); // Use CSS class for styling

            setTimeout(function() {
                copyBtn.textContent = originalBtnText; // Restore original text
                copyBtn.classList.remove('copied-success');
            }, 2000);
        }).catch(function(err) {
            console.error('无法复制文本: ', err);
            copyBtn.textContent = '复制失败';
            copyBtn.classList.add('copied-error'); // Use CSS class for styling

            // Optionally alert, or rely on button text/style
            // alert('复制失败，请手动复制。');

            setTimeout(function() {
                copyBtn.textContent = originalBtnText; // Restore original text
                copyBtn.classList.remove('copied-error');
            }, 3000); // Show error state a bit longer
        });
    });

    // Note: The commented-out basic status message styling from your original script
    // is now fully handled by the .status-message .error, .success, .info classes in style.css
    // and the updateStatus helper function.
});
