# Speech-To-Text 音频转录校准工具

## 项目简介

一个简单而强大的语音转文字应用，支持多种语音识别 API 接入进行音频转录，并可调用 OpenAI 格式 API 进行校准优化。

## 功能特点

- 🎤 支持上传音频文件进行转写
- 🔌 支持多种语音识别服务
- ✒️ 支持对转录结果进行校准优化
- 🚀 支持docker部署
- 🌐 简洁的 Web 界面
- 🔒 通过环境变量配置 API 信息

## 重大更新
### 20250607更新
- 新增**量子速读**功能：一键生成摘要。支持切换显示 原文/摘要。
---
### 20250606更新
- 引入**自动分块**机制: 自动检测长文本，当转录稿超过设定长度时，智能分割成多个语义完整的文本块。避免超出 API Token 限制。
- 引入**上下文感知**机制 : 在处理每个文本块时，将前一文本块的结尾部分作为上下文提示，一并发送给 AI 模型。确保最终文本的连贯性和风格一致性。
- 引入**并发校准**机制: 多线程并发处理，可同时向校准服务 API 发送多个文本块的请求（当前并发数为3）。缩短超长文本的总体处理时间。
- 引入**自动重试**机制: 在单文本块未成功校准时，自动进行最多3次重试。

## 前端预览
![image](https://github.com/user-attachments/assets/c27411d8-2e71-4194-ba9c-217787fae8bb)

## 快速开始

### 自行构建 Docker

1. **构建镜像**:

    ```bash
    docker build -t speech-to-text .
    ```

2. **部署容器**:

    ```bash
    version: '3.8'
    services:
      speech-to-text:
        image: speech-to-text:latest
        container_name: speech-to-text
        environment:
          - S2T_API_URL = your-speech-to-text-api-endpoint-url
          # 语音转录 API 地址，可选配置，默认是硅基(https://api.siliconflow.cn/v1/audio/transcriptions)
          - S2T_API_KEY = your-speech-to-text-api-key
          # 语音转录 API Key，必须配置
          - S2T_MODEL = your-speech-to-text-model
          # 语音转录模型，可选配置，默认是 FunAudioLLM/SenseVoiceSmall
          - OPT_API_URL = your-text-optimizing-api-endpoint-url
          # 文本校准优化 API 地址，可选配置，不配置不启用优化，直接转出转录结果
          - OPT_API_KEY = your-text-optimizing-api-key
          # 文本校准优化 API Key
          - OPT_MODE = your-text-optimizing-model
          # 文本校准优化模型
        ports:
          - "your-port:5000"
    ```

## 技术栈

- 后端：Python Flask
- 前端：HTML, CSS, JavaScript

## 许可证

MIT License

