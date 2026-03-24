# YinShield

English | [简体中文](./README.zh-CN.md)

YinShield is a local de-identification gateway for AI workflows.

Current shipping forms:
- PyPI package: `yinshield`
- Local HTTP service: `yinshield serve`
- Thin OpenClaw plugin: `@serein-213/openclaw-yinshield`

## Status

- Recommended release position: `0.1.0 alpha`
- Recommended default path: `mode="placeholder"`
- Best-fit scenarios today: Chinese customer support, enterprise copilots, internal agents, and any workflow that needs sensitive fields masked before a request leaves the host
- Clearest production boundary today: mask locally first, send the model request second, restore readable output locally after inference
- Still being tuned: `mode="alias"` recovery and false-positive control on more realistic English distributions

## What Works Now

- Chinese and English PII masking: Chinese names, English names, mobile phone numbers, US phone numbers, Chinese ID cards, SSNs, email, WeChat IDs, bank cards, bank accounts, bank names, landlines, license plates, passports, unified social credit codes, tax IDs, company names, addresses, birthdates, DOB, IP addresses, VIN, EIN, medical record IDs, MRN, order numbers, tracking numbers, customer IDs, member IDs, and contract numbers
- Two replacement modes:
  - `mode="placeholder"`: `Zhang San -> <PERSON_1>`
  - `mode="alias"`: `Zhang San -> Chen Ming`
- Three strategy levels:
  - `loose`: high-confidence entities only
  - `balanced`: default, suitable for general conversations and customer-support text
  - `strict`: broader coverage for contextual entities and business identifiers
- Deterministic placeholders: `placeholder` mode is the better default for production flows that need debuggable, auditable, reproducible masking
- Session-scoped stable mappings: the same entity can keep the same replacement across turns, and mappings can be persisted locally
- Local re-identification: mappings and restoration logic stay on the local side instead of being delegated to third-party services
- OpenAI-compatible integrations:
  - `ShieldedOpenAI`
  - `ShieldedAsyncOpenAI`
  - `chat.completions`
  - `responses`
  - `stream=True`
  - `base_url=...`
- Local HTTP service:
  - `POST /health`
  - `POST /mask`
  - `POST /unmask`
  - `POST /messages/mask`
- OpenClaw integration:
  - `yinshield_mask`
  - `yinshield_unmask`
  - `yinshield_shield_messages`

## Installation

```bash
pip install yinshield
```

For local release validation:

```bash
python -m unittest discover -s tests -v
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode placeholder --strategy strict --output benchmarks/mini_realistic_results.placeholder.json
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode alias --strategy strict --output benchmarks/mini_realistic_results.alias.json
node --check openclaw-plugin/src/index.js
python -m build
```

## Release

Prepare the next release version:

```bash
python scripts/sync_release_version.py 0.1.0
python scripts/check_version_consistency.py
```

Full release steps are documented in [RELEASE.md](./RELEASE.md).

Alpha release notes:
- [0.1.0-alpha](./docs/release-notes/0.1.0-alpha.md)

## Quick Start For OpenClaw

```bash
pip install yinshield
python -m yinshield.install_openclaw
openclaw plugins install @serein-213/openclaw-yinshield
openclaw plugins enable openclaw-yinshield
yinshield serve
```

`python -m yinshield.install_openclaw` will:
- generate an auth token
- scaffold the OpenClaw plugin config
- print the exact `yinshield serve --auth-token ...` command to run

Installed CLI alias:

```bash
yinshield-install-openclaw
```

Shell bootstrap for users who prefer a one-shot script:

```bash
bash scripts/setup-openclaw-yinshield.sh
```

If you later host this script, the curl-style entry can be:

```bash
curl -fsSL https://your-domain/setup-openclaw-yinshield.sh | bash
```

OpenClaw plugin config:

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

## Basic Usage

```python
from yinshield import Shield, ShieldSession

shield = Shield(
    mode="placeholder",   # or "alias"
    strategy="balanced",  # loose | balanced | strict
)

session = ShieldSession()
raw_text = "Recipient: Zhang San, phone 13812345678, address 88 Jianguo Road, Chaoyang District, Beijing."

masked_text, mapping = shield.mask(raw_text, session=session)
print(masked_text)

restored = shield.unmask(masked_text, session=session)
print(restored)
```

## Session Persistence

```python
from yinshield import Shield

shield = Shield(mode="alias", strategy="strict")
shield.mask("Contact: Wang Xiaoming, phone 13812345678.")
shield.save_session("yinshield-session.json")

another = Shield(mode="alias", strategy="strict")
another.load_session("yinshield-session.json")
masked, _ = another.mask("Please contact Wang Xiaoming again, phone 13812345678.")
```

## Local HTTP Service

Start the bridge:

```bash
yinshield serve
```

Default bind:
- host: `127.0.0.1`
- port: `27811`

Custom bind:

```bash
yinshield serve --host 127.0.0.1 --port 27811 --mode placeholder --strategy balanced --auth-token change-me
```

HTTP API:

`POST /health`

```json
{}
```

`POST /mask`

```json
{
  "text": "My name is Zhang San, phone 13812345678",
  "mode": "placeholder",
  "session_id": "chat-1"
}
```

`POST /unmask`

```json
{
  "text": "My name is <PERSON_1>, phone <PHONE_1>",
  "mapping": {
    "<PERSON_1>": "Zhang San",
    "<PHONE_1>": "13812345678"
  }
}
```

`POST /messages/mask`

```json
{
  "messages": [
    { "role": "user", "content": "My name is Zhang San, phone 13812345678" },
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "Order number 20240324ABC123" }
      ]
    }
  ],
  "mode": "placeholder",
  "session_id": "chat-1"
}
```

Notes:
- HTTP service is stateless by default
- To reuse aliases or placeholders across turns, pass `session_id`
- If `--auth-token` is omitted, `yinshield serve` generates a temporary token and prints it
- To protect the local service, send `Authorization: Bearer <token>`

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
        {"role": "user", "content": "My name is Zhang San, my phone is 13812345678"}
    ],
)

print(response.choices[0].message.content)
# Request is masked before send, output is restored after response
```

Current wrapper coverage:
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
    input="My name is Zhang San, my phone is 13812345678",
)

print(response.output_text)
```

## CLI

```bash
python -m yinshield --mode alias --strategy strict --session-file .yinshield.json \
  "Recipient: Zhang San, phone 13812345678, order number 20240324ABC123"
```

Run local service:

```bash
yinshield serve --session-file .yinshield-http-session.json
```

## OpenClaw Installer

```bash
python -m yinshield.install_openclaw
```

Equivalent installed command:

```bash
yinshield-install-openclaw
```

Preview without writing files:

```bash
python -m yinshield.install_openclaw --print-only
```

## Benchmark

Local benchmark script:

```bash
python benchmarks/run_benchmark.py --mode placeholder --strategy strict
python benchmarks/run_benchmark.py --mode alias --strategy strict
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode placeholder --strategy strict --output benchmarks/mini_realistic_results.placeholder.json
python benchmarks/run_benchmark.py --dataset benchmarks/mini_realistic_dataset.json --mode alias --strategy strict --output benchmarks/mini_realistic_results.alias.json
```

Current sample-set results:
- `placeholder + strict`: `precision=1.0 recall=1.0 false_positive_rate=0.0 recovery_rate=1.0 semantic_proxy=0.3662`
- `alias + strict`: `precision=1.0 recall=1.0 false_positive_rate=0.0 recovery_rate=1.0 semantic_proxy=0.8182`

Mini realistic-set results:
- `placeholder + strict`: `precision=0.9765 recall=0.9765 false_positive_rate=0.0645 recovery_rate=1.0 semantic_proxy=0.321`
- `alias + strict`: `precision=0.954 recall=0.9765 false_positive_rate=0.129 recovery_rate=0.9032 semantic_proxy=0.75`

The current sample set includes:
- Chinese identity and business identifiers
- English names, US phone, SSN, DOB, EIN, MRN, tracking number
- Mixed Chinese-English names and addresses
- English address variants such as `Apt/Unit/Suite`
- Negative-set false-positive checks

The mini realistic set adds:
- 30 small samples closer to real-world distribution
- Chinese customer support, finance, medical, and logistics cases
- English customer profile, compliance, medical, and logistics cases
- Mixed Chinese-English text
- Stricter negative samples and recovery-rate checks

`semantic_proxy` is only a local format-preservation heuristic, not a downstream LLM task benchmark.

## Coverage Audit

Current rule coverage is closer to "high-frequency explicit-field masking for Chinese-English business text plus light contextual recognition", not general semantic NER.

Supported:
- Basic identity information: Chinese names, English names, mobile phone numbers, US phone numbers, Chinese ID cards, SSNs, birthdates, DOB, email, WeChat IDs
- Address and location: common Chinese address patterns, English street addresses, English `Apt/Unit/Suite` variants
- Enterprise and finance: company names, unified social credit codes, tax IDs, EIN, bank cards, bank accounts, bank names
- Transport and devices: license plates, passports, VIN, IPv4 addresses
- Medical and business identifiers: medical record numbers, MRN, order numbers, tracking numbers, customer IDs, member IDs, contract numbers

Partially supported:
- Chinese personal names: strong on contexts such as "my name is", "contact", "recipient", or "patient"; still limited in fully natural narrative sentences
- Chinese addresses: strong on province-city-district-road-number formats; still limited on colloquial references, campus/park abbreviations, or short addresses without administrative prefixes
- English names and company names: stable on explicit fields and some natural sentences; still limited on complex long sentences, abbreviations, and cross-sentence references
- `alias` mode: still weaker than `placeholder` on recovery rate and false positives for more realistic English company-name and address distributions
- Enterprise information: company names and unified social credit code / EIN are stable; legal representatives, account names, and business-license IDs are not yet covered

Not yet supported or still weak:
- MAC addresses, GPS coordinates, and precise geolocation
- Invoice numbers, device serial numbers, organization codes, and more vehicle fields beyond license plates
- General semantic entity recognition, entity disambiguation, and weak-context inference

## Next

- Better English entity support
- OpenClaw auto-start for the local service
- More robust contextual recognition and entity boundaries
- Anthropic / LiteLLM / LangChain integrations
- More realistic downstream semantic evaluation

## License

[Apache-2.0 License](LICENSE)
