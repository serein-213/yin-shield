# OpenClaw YinShield Plugin

Thin OpenClaw plugin that forwards masking requests to a local `yinshield serve` process.

## Install

```bash
bash scripts/setup-openclaw-yinshield.sh
```

Manual path:

```bash
openclaw plugins install @serein-213/openclaw-yinshield
openclaw plugins enable openclaw-yinshield
```

## Config

```json
{
  "plugins": {
    "entries": {
      "openclaw-yinshield": {
        "enabled": true,
        "config": {
          "baseUrl": "http://127.0.0.1:27811",
          "mode": "placeholder",
          "authToken": "change-me",
          "timeoutMs": 10000
        }
      }
    }
  }
}
```

## Tools

- `yinshield_mask`
- `yinshield_unmask`
- `yinshield_shield_messages`

Use `session_id` in tool inputs if you want cross-turn consistent aliases/placeholders.

If the local service is unavailable, the plugin tells the user to run `yinshield serve`.
