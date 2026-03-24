# YinShield

[English](./README.md) | 简体中文

YinShield 是一个面向 AI 工作流的本地脱敏网关。

当前发布形态：
- PyPI 包：`yinshield`
- 本地 HTTP 服务：`yinshield serve`
- OpenClaw 薄插件：`@serein-213/openclaw-yinshield`

## 当前状态

- 当前建议发布定位：`0.1.0 alpha`
- 当前最推荐的默认路径：`mode="placeholder"`
- 当前最适合的场景：中文客服、企业助手、内部 Agent，以及任何需要在请求离开主机前先处理敏感字段的工作流
- 当前最清晰的生产边界：先本地脱敏，再发模型请求，最后在本地恢复可读结果
- 当前仍在持续打磨的部分：`mode="alias"` 在更真实英文分布下的恢复率与误伤控制

## 当前已可用能力

- 中英 PII 脱敏：中文姓名、英文姓名、手机号、US phone、身份证、SSN、邮箱、微信号、银行卡、银行账号、开户行、座机、车牌、护照、统一社会信用代码、税号、公司名、地址、生日、DOB、IP 地址、VIN、EIN、病历号、MRN、订单号、快递单号、tracking number、客户号、会员号、合同号
- 两种替换模式：
  - `mode="placeholder"`：`张三 -> <PERSON_1>`
  - `mode="alias"`：`张三 -> 陈明`
- 三档策略：
  - `loose`：只处理高置信实体
  - `balanced`：默认，适合一般对话和客服文本
  - `strict`：覆盖更多上下文实体和业务编号
- 确定性占位符：`placeholder` 模式更适合需要可调试、可验证、可回溯的生产工作流
- 会话级稳定映射：同一实体可在多轮中保持一致替换，并支持持久化到文件
- 本地重识别：映射关系和还原逻辑留在本地侧，不需要把原始标识信息交给第三方服务
- OpenAI-compatible 接入：
  - `ShieldedOpenAI`
  - `ShieldedAsyncOpenAI`
  - `chat.completions`
  - `responses`
  - `stream=True`
  - `base_url=...`
- 本地 HTTP 服务：
  - `POST /health`
  - `POST /mask`
  - `POST /unmask`
  - `POST /messages/mask`
- OpenClaw 集成：
  - `yinshield_mask`
  - `yinshield_unmask`
  - `yinshield_shield_messages`

## 安装

```bash
pip install yinshield
```

本地发布验证：

```bash
python -m unittest discover -s tests -v
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode placeholder --strategy strict --output benchmarks/mini_realistic_results.placeholder.json
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode alias --strategy strict --output benchmarks/mini_realistic_results.alias.json
node --check openclaw-plugin/src/index.js
python -m build
```

## 发布

准备下一个版本号：

```bash
python scripts/sync_release_version.py 0.1.0
python scripts/check_version_consistency.py
```

完整发布步骤见 [RELEASE.md](./RELEASE.md)。

Alpha 发布说明：
- [0.1.0-alpha](./docs/release-notes/0.1.0-alpha.md)

## OpenClaw 快速开始

```bash
pip install yinshield
python -m yinshield.install_openclaw
openclaw plugins install @serein-213/openclaw-yinshield
openclaw plugins enable openclaw-yinshield
yinshield serve
```

`python -m yinshield.install_openclaw` 会：
- 生成鉴权 token
- 写入 OpenClaw 插件配置
- 打印准确的 `yinshield serve --auth-token ...` 启动命令

安装后的 CLI 别名：

```bash
yinshield-install-openclaw
```

如果你更喜欢一键脚本：

```bash
bash scripts/setup-openclaw-yinshield.sh
```

如果后续你把这个脚本托管到公网，也可以使用：

```bash
curl -fsSL https://your-domain/setup-openclaw-yinshield.sh | bash
```

OpenClaw 插件配置示例：

```json
{
  "plugins": {
    "entries": {
      "openclaw-yinshield": {
        "enabled": true,
        "config": {
          "baseUrl": "http://127.0.0.1:27811",
          "mode": "placeholder",
          "authToken": "change-me"
        }
      }
    }
  }
}
```

## 基本用法

```python
from yinshield import Shield, ShieldSession

shield = Shield(
    mode="placeholder",   # 或 "alias"
    strategy="balanced",  # loose | balanced | strict
)

session = ShieldSession()
raw_text = "收件人：张三，手机号13812345678，收货地址：北京市朝阳区建国路88号。"

masked_text, mapping = shield.mask(raw_text, session=session)
print(masked_text)

restored = shield.unmask(masked_text, session=session)
print(restored)
```

## 会话持久化

```python
from yinshield import Shield

shield = Shield(mode="alias", strategy="strict")
shield.mask("联系人：王小明，手机号13812345678。")
shield.save_session("yinshield-session.json")

another = Shield(mode="alias", strategy="strict")
another.load_session("yinshield-session.json")
masked, _ = another.mask("请再次联系王小明，手机号13812345678。")
```

## 本地 HTTP 服务

启动 bridge：

```bash
yinshield serve
```

默认绑定：
- host: `127.0.0.1`
- port: `27811`

自定义绑定：

```bash
yinshield serve --host 127.0.0.1 --port 27811 --mode placeholder --strategy balanced --auth-token change-me
```

HTTP API：

`POST /health`

```json
{}
```

`POST /mask`

```json
{
  "text": "我叫张三，手机号13812345678",
  "mode": "placeholder",
  "session_id": "chat-1"
}
```

`POST /unmask`

```json
{
  "text": "我叫<PERSON_1>，手机号<PHONE_1>",
  "mapping": {
    "<PERSON_1>": "张三",
    "<PHONE_1>": "13812345678"
  }
}
```

`POST /messages/mask`

```json
{
  "messages": [
    { "role": "user", "content": "我叫张三，手机号13812345678" },
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "订单号20240324ABC123" }
      ]
    }
  ],
  "mode": "placeholder",
  "session_id": "chat-1"
}
```

说明：
- HTTP 服务默认无状态
- 如果你希望多轮复用别名或占位符，请传入 `session_id`
- 若未传 `--auth-token`，`yinshield serve` 会生成临时 token 并打印出来
- 保护本地服务时，请发送 `Authorization: Bearer <token>`

## OpenAI-Compatible Wrapper

```python
from yinshield import ShieldedOpenAI

client = ShieldedOpenAI(
    api_key="YOUR_OPENAI_API_KEY",
    base_url="https://api.openai.com/v1",  # DeepSeek / OpenAI-compatible providers also work
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "我叫张三，手机号是13812345678"}
    ],
)

print(response.choices[0].message.content)
# 请求发送前自动脱敏，返回内容自动还原
```

当前 wrapper 覆盖范围：
- `client.chat.completions.create(...)`
- `client.chat.completions.create(..., stream=True)`
- `client.responses.create(...)`
- `client.responses.create(..., stream=True)`
- `await async_client.chat.completions.create(...)`
- `await async_client.responses.create(...)`

## Async Wrapper

```python
from yinshield import ShieldedAsyncOpenAI

client = ShieldedAsyncOpenAI(api_key="YOUR_OPENAI_API_KEY")

response = await client.responses.create(
    model="gpt-4.1-mini",
    input="我叫张三，手机号13812345678",
)

print(response.output_text)
```

## CLI

```bash
python -m yinshield --mode alias --strategy strict --session-file .yinshield.json \
  "收件人：张三，手机号13812345678，订单号20240324ABC123"
```

运行本地服务：

```bash
yinshield serve --session-file .yinshield-http-session.json
```

## OpenClaw 安装器

```bash
python -m yinshield.install_openclaw
```

等价的已安装命令：

```bash
yinshield-install-openclaw
```

只预览、不写文件：

```bash
python -m yinshield.install_openclaw --print-only
```

## Benchmark

本地 benchmark 脚本：

```bash
python benchmarks/run_benchmark.py --mode placeholder --strategy strict
python benchmarks/run_benchmark.py --mode alias --strategy strict
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode placeholder --strategy strict --output benchmarks/mini_realistic_results.placeholder.json
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode alias --strategy strict --output benchmarks/mini_realistic_results.alias.json
```

当前 sample set 结果：
- `placeholder + strict`: `precision=1.0 recall=1.0 false_positive_rate=0.0 recovery_rate=1.0 semantic_proxy=0.3662`
- `alias + strict`: `precision=1.0 recall=1.0 false_positive_rate=0.0 recovery_rate=1.0 semantic_proxy=0.8182`

当前 mini realistic set 结果：
- `placeholder + strict`: `precision=0.9765 recall=0.9765 false_positive_rate=0.0645 recovery_rate=1.0 semantic_proxy=0.321`
- `alias + strict`: `precision=0.954 recall=0.9765 false_positive_rate=0.129 recovery_rate=0.9032 semantic_proxy=0.75`

当前 sample set 包含：
- 中文身份与业务编号
- 英文姓名、US phone、SSN、DOB、EIN、MRN、tracking number
- 中英混合姓名与地址
- 英文地址 `Apt/Unit/Suite` 变体
- 负样例误伤检查

mini realistic set 额外包含：
- 30 条更接近真实分布的小评测样本
- 中文客服 / 金融 / 医疗 / 物流
- 英文客户资料 / 合规 / 医疗 / 物流
- 中英混合文本
- 更严格的负样例和恢复率检查

`semantic_proxy` 只是本地格式保留启发式指标，不是下游 LLM 任务 benchmark。

## 覆盖度审计

当前规则覆盖度更接近“中英业务文本的高频显式字段脱敏 + 弱语义上下文识别”，不是通用语义 NER。

已支持：
- 基础身份信息：中文姓名、英文姓名、手机号、US phone、身份证、SSN、生日、DOB、邮箱、微信号
- 地址与位置：中文住址变体、英文街道地址、`Apt/Unit/Suite` 类英文地址
- 企业与金融：公司名称、统一社会信用代码、税号、EIN、银行卡、银行账号、开户行
- 交通与设备：车牌、护照、VIN、IPv4 地址
- 医疗与业务编号：病历号、MRN、订单号、快递单号、tracking number、客户号、会员号、合同号

部分支持：
- 中文姓名：对“我叫 / 联系人 / 收件人 / 患者”等上下文较强，对自然叙述句中的姓名识别仍有限
- 中文地址：对“省市区路号”类格式较强，对口语化、园区 / 楼宇简称、缺少行政区前缀的短地址仍有限
- 英文姓名与公司名：对显式字段和部分自然句式较稳，但复杂长句、缩写、跨句引用仍有限
- `alias` 模式：在更真实的英文公司名和英文地址场景下，恢复率和误伤率仍弱于 `placeholder`
- 企业信息：公司名称和统一社会信用代码 / EIN 较稳，但法人、开户名、营业执照号等尚未覆盖

未支持或仍较弱：
- MAC / GPS 坐标 / 精确地理位置
- 发票号、设备序列号、组织机构代码、车牌以外更多车辆字段
- 真正的语义实体识别、实体消歧、弱上下文推断

## Next

- 更强的英文实体支持
- OpenClaw 自动拉起本地服务
- 更稳的上下文识别和实体边界
- Anthropic / LiteLLM / LangChain 接入
- 更真实的下游语义评测

## 许可证

[Apache-2.0 License](LICENSE)
