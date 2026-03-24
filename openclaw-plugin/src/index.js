const DEFAULT_CONFIG = {
  baseUrl: "http://127.0.0.1:27811",
  mode: "placeholder",
  timeoutMs: 10000,
  authToken: "",
  autoStart: false,
};

const PLUGIN_ID = "openclaw-yinshield";

function resolvePluginConfig(api, ctx) {
  const candidates = [
    ctx?.pluginConfig,
    ctx?.config?.plugins?.entries?.[PLUGIN_ID]?.config,
    api?.config?.plugins?.entries?.[PLUGIN_ID]?.config,
    api?.pluginConfig?.[PLUGIN_ID],
  ];
  for (const candidate of candidates) {
    if (candidate && typeof candidate === "object") {
      return { ...DEFAULT_CONFIG, ...candidate };
    }
  }
  return { ...DEFAULT_CONFIG };
}

async function callYinShield(path, payload, config) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.timeoutMs);
  try {
    const headers = { "Content-Type": "application/json" };
    if (config.authToken) {
      headers.Authorization = `Bearer ${config.authToken}`;
    }
    const response = await fetch(`${config.baseUrl}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data.error || `${path} failed with status ${response.status}`;
      if (response.status === 401) {
        throw new Error(`YinShield authentication failed: ${message}`);
      }
      throw new Error(`YinShield request failed (${response.status}): ${message}`);
    }
    return data;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("YinShield request failed")) {
      throw error;
    }
    if (error instanceof Error && error.message.startsWith("YinShield authentication failed")) {
      throw error;
    }
    if (error?.name === "AbortError") {
      throw new Error(
        `YinShield service timed out after ${config.timeoutMs}ms. Start or check it with: yinshield serve`
      );
    }
    throw new Error(
      `Unable to reach YinShield at ${config.baseUrl}. Start it with: yinshield serve`
    );
  } finally {
    clearTimeout(timer);
  }
}

function makeTextResult(text, extra = {}) {
  return {
    content: [{ type: "text", text }],
    structuredContent: extra,
  };
}

export default {
  id: PLUGIN_ID,
  name: "YinShield",
  register(api) {
    api.registerTool({
      name: "yinshield_mask",
      description: "Mask Chinese sensitive text through the local YinShield service.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          text: { type: "string" },
          mode: { type: "string", enum: ["placeholder", "alias"] },
          session_id: { type: "string" },
          mapping: { type: "object", additionalProperties: { type: "string" } },
        },
        required: ["text"],
      },
      inputSchema: {
        type: "object",
        additionalProperties: false,
        properties: {
          text: { type: "string" },
          mode: { type: "string", enum: ["placeholder", "alias"] },
          session_id: { type: "string" },
          mapping: { type: "object", additionalProperties: { type: "string" } },
        },
        required: ["text"],
      },
      async execute(_id, params, ctx) {
        const config = resolvePluginConfig(api, ctx);
        const result = await callYinShield(
          "/mask",
          {
            text: params.text,
            mode: params.mode || config.mode,
            session_id: params.session_id,
            mapping: params.mapping,
          },
          config
        );
        return makeTextResult(result.text, result);
      },
    });

    api.registerTool({
      name: "yinshield_unmask",
      description: "Restore YinShield-masked text through the local YinShield service.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          text: { type: "string" },
          mapping: { type: "object", additionalProperties: { type: "string" } },
        },
        required: ["text", "mapping"],
      },
      inputSchema: {
        type: "object",
        additionalProperties: false,
        properties: {
          text: { type: "string" },
          mapping: { type: "object", additionalProperties: { type: "string" } },
        },
        required: ["text", "mapping"],
      },
      async execute(_id, params, ctx) {
        const config = resolvePluginConfig(api, ctx);
        const result = await callYinShield(
          "/unmask",
          {
            text: params.text,
            mapping: params.mapping,
          },
          config
        );
        return makeTextResult(result.text, result);
      },
    });

    api.registerTool({
      name: "yinshield_shield_messages",
      description: "Mask chat-style message arrays through the local YinShield service.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          messages: { type: "array" },
          mode: { type: "string", enum: ["placeholder", "alias"] },
          session_id: { type: "string" },
          mapping: { type: "object", additionalProperties: { type: "string" } },
        },
        required: ["messages"],
      },
      inputSchema: {
        type: "object",
        additionalProperties: false,
        properties: {
          messages: { type: "array" },
          mode: { type: "string", enum: ["placeholder", "alias"] },
          session_id: { type: "string" },
          mapping: { type: "object", additionalProperties: { type: "string" } },
        },
        required: ["messages"],
      },
      async execute(_id, params, ctx) {
        const config = resolvePluginConfig(api, ctx);
        const result = await callYinShield(
          "/messages/mask",
          {
            messages: params.messages,
            mode: params.mode || config.mode,
            session_id: params.session_id,
            mapping: params.mapping,
          },
          config
        );
        return makeTextResult("Masked message payload ready.", result);
      },
    });
  },
};
