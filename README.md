# Speech-to-Text 音频转录校准工具

## 项目简介

一个简单而强大的语音转文字应用，支持多种语音识别 API 接入进行音频转录，并可调用 OpenAI 格式 API 进行校准优化。

## 功能特点

- 🎤 支持上传音频文件进行转写
- 🔌 支持多种语音识别服务
- ✒️ 支持对转录结果进行校准优化
- 🚀 支持docker部署
- 🌐 简洁的 Web 界面
- 🔒 通过环境变量配置 API 信息

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
        image: speech-to-test:latest
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

