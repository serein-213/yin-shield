# 🛡️ YinShield (隐)

**Make your data invisible to AI, like a shadow.**  
**让你的数据对 AI 隐形，如影随形。**

[![PyPI version](https://img.shields.io/pypi/v/yinshield.svg)](https://pypi.org/project/yinshield/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

---

## ☯️ What is YinShield? | 什么是隐盾？

**Yin (隐)** in Chinese means *Hidden* or *Invisible*. 

**YinShield** is a lightweight, zero-config Python library designed to protect your privacy when using AI APIs (like OpenAI, DeepSeek, Claude). It intercepts sensitive information locally, replaces it with semantically-consistent tokens, and restores it automatically after the AI responds.

**隐盾 (YinShield)** 是一款轻量级、零配置的 Python 库，专为保护 AI API 使用过程中的隐私而生。它在本地拦截敏感信息，将其替换为保持语义一致的占位符，并在 AI 回复后自动还原。

### 🌟 Key Features | 核心特性

- **🚀 Zero Config**: `pip install` and you are ready. No complex setups or local servers required.
- **🧠 Semantic Preservation**: Unlike brute-force masking, YinShield uses "Semantic Aliases" (e.g., replacing "Zhang San" with "Li Si") to keep the AI's reasoning capabilities intact.
- **🔒 Local-First**: All detection and masking happen on your machine. No sensitive data ever leaves your device.
- **🇨🇳 Optimized for China**: Built-in support for Chinese-specific PII (WeChat ID, ID cards, Chinese addresses, etc.).
- **🔌 Drop-in Replacement**: Seamlessly integrates with your existing AI SDK calls.

---

## 🛠️ Quick Start | 快速上手

### Installation | 安装
```bash
pip install yinshield
```

### Basic Usage | 基本用法 (Coming Soon)
```python
from yinshield import Shield

# Initialize the shield
shield = Shield()

raw_text = "我叫张三，我的手机号是13812345678，我住在北京市朝阳区。"

# 1. Locally mask sensitive data
masked_text, mapping = shield.mask(raw_text)
# masked_text becomes: "我叫<PERSON_1>，我的手机号是<PHONE_1>，我住在<LOC_1>。"

# 2. Call your AI API with masked_text...
# (AI processes the data without knowing who you are)

# 3. Restore the response locally
final_response = shield.unmask(ai_response, mapping)
```

---

## 🗺️ Roadmap | 开发路线图

- [ ] v0.1.0: Core Regex-based Chinese PII masking.
- [ ] v0.2.0: Lightweight ONNX model integration for high-accuracy NER.
- [ ] v0.3.0: Semantic Alias engine (Consistent persona mapping).
- [ ] v0.4.0: Image/OCR privacy protection.

---

## 🤝 Contributing | 贡献

YinShield is an open-source project. We welcome contributions to help make AI safer for everyone!

## 📄 License | 许可证

[Apache-2.0 License](LICENSE)
