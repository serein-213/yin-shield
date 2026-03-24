import unittest

from yinshield.openai import ShieldedAsyncOpenAI, ShieldedOpenAI


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeStreamEvent:
    def __init__(self, delta):
        self.choices = [FakeChoice(delta)]


class FakeCompletions:
    def __init__(self):
        self.last_messages = None

    def create(self, *args, **kwargs):
        self.last_messages = kwargs["messages"]
        if kwargs.get("stream"):
            return [
                FakeStreamEvent("已记录 <PERSON_1>"),
                FakeStreamEvent(" 的手机号 <PHONE_1>"),
            ]
        return FakeResponse("已记录 <PERSON_1> 的手机号 <PHONE_1>")


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeResponsesResult:
    def __init__(self, text):
        self.output_text = text
        self.output = [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": text},
                ],
            }
        ]


class FakeResponses:
    def __init__(self):
        self.last_input = None

    def create(self, *args, **kwargs):
        self.last_input = kwargs["input"]
        if kwargs.get("stream"):
            return [
                {"output_text": "你好 <PERSON_1>"},
                {"output_text": "，手机号 <PHONE_1> 已收到"},
            ]
        return FakeResponsesResult("你好 <PERSON_1>，手机号 <PHONE_1> 已收到")


class AsyncListStream:
    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class FakeAsyncCompletions:
    def __init__(self):
        self.last_messages = None

    async def create(self, *args, **kwargs):
        self.last_messages = kwargs["messages"]
        if kwargs.get("stream"):
            return AsyncListStream(
                [
                    FakeStreamEvent("已记录 <PERSON_1>"),
                    FakeStreamEvent(" 的手机号 <PHONE_1>"),
                ]
            )
        return FakeResponse("已记录 <PERSON_1> 的手机号 <PHONE_1>")


class FakeAsyncChat:
    def __init__(self):
        self.completions = FakeAsyncCompletions()


class FakeAsyncResponses:
    def __init__(self):
        self.last_input = None

    async def create(self, *args, **kwargs):
        self.last_input = kwargs["input"]
        if kwargs.get("stream"):
            return AsyncListStream(
                [
                    {"output_text": "你好 <PERSON_1>"},
                    {"output_text": "，手机号 <PHONE_1> 已收到"},
                ]
            )
        return FakeResponsesResult("你好 <PERSON_1>，手机号 <PHONE_1> 已收到")


class FakeAsyncClient:
    def __init__(self):
        self.chat = FakeAsyncChat()
        self.responses = FakeAsyncResponses()


class FakeClient:
    def __init__(self):
        self.chat = FakeChat()
        self.responses = FakeResponses()


class ShieldedOpenAITests(unittest.TestCase):
    def test_masks_request_and_unmasks_response_for_string_content(self):
        client = FakeClient()
        wrapped = ShieldedOpenAI(client=client)

        response = wrapped.chat.completions.create(
            model="fake-model",
            messages=[{"role": "user", "content": "我叫张三，手机号13812345678"}],
        )

        self.assertEqual(
            client.chat.completions.last_messages[0]["content"],
            "我叫<PERSON_1>，手机号<PHONE_1>",
        )
        self.assertEqual(response.choices[0].message.content, "已记录 张三 的手机号 13812345678")

    def test_masks_text_parts_and_preserves_non_text_parts(self):
        client = FakeClient()
        wrapped = ShieldedOpenAI(client=client)

        wrapped.chat.completions.create(
            model="fake-model",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "我是李四，手机号13900001111"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                    ],
                }
            ],
        )

        parts = client.chat.completions.last_messages[0]["content"]
        self.assertEqual(parts[0]["text"], "我是<PERSON_1>，手机号<PHONE_1>")
        self.assertEqual(parts[1]["image_url"]["url"], "https://example.com/a.png")

    def test_unmasks_chat_stream_events(self):
        client = FakeClient()
        wrapped = ShieldedOpenAI(client=client)

        stream = wrapped.chat.completions.create(
            model="fake-model",
            messages=[{"role": "user", "content": "我叫张三，手机号13812345678"}],
            stream=True,
        )

        chunks = [event.choices[0].message.content for event in stream]
        self.assertEqual(chunks, ["已记录 张三", " 的手机号 13812345678"])

    def test_masks_responses_api_input_and_unmasks_output(self):
        client = FakeClient()
        wrapped = ShieldedOpenAI(client=client)

        response = wrapped.responses.create(
            model="fake-model",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "我是李四，手机号13900001111"},
                    ],
                }
            ],
        )

        self.assertEqual(
            client.responses.last_input[0]["content"][0]["text"],
            "我是<PERSON_1>，手机号<PHONE_1>",
        )
        self.assertEqual(response.output_text, "你好 李四，手机号 13900001111 已收到")
        self.assertEqual(
            response.output[0]["content"][0]["text"],
            "你好 李四，手机号 13900001111 已收到",
        )

    def test_unmasks_responses_stream_events(self):
        client = FakeClient()
        wrapped = ShieldedOpenAI(client=client)

        stream = wrapped.responses.create(
            model="fake-model",
            input="我叫张三，手机号13812345678",
            stream=True,
        )

        chunks = [event["output_text"] for event in stream]
        self.assertEqual(chunks, ["你好 张三", "，手机号 13812345678 已收到"])

    def test_session_persists_across_calls(self):
        client = FakeClient()
        wrapped = ShieldedOpenAI(client=client)

        wrapped.chat.completions.create(
            model="fake-model",
            messages=[{"role": "user", "content": "联系人：张三，手机号13812345678"}],
        )
        wrapped.chat.completions.create(
            model="fake-model",
            messages=[{"role": "user", "content": "请继续联系张三，手机号13812345678"}],
        )

        self.assertIn("<PERSON_1>", client.chat.completions.last_messages[0]["content"])
        self.assertIn("<PHONE_1>", client.chat.completions.last_messages[0]["content"])


class ShieldedAsyncOpenAITests(unittest.IsolatedAsyncioTestCase):
    async def test_masks_request_and_unmasks_async_response(self):
        client = FakeAsyncClient()
        wrapped = ShieldedAsyncOpenAI(client=client)

        response = await wrapped.chat.completions.create(
            model="fake-model",
            messages=[{"role": "user", "content": "我叫张三，手机号13812345678"}],
        )

        self.assertEqual(
            client.chat.completions.last_messages[0]["content"],
            "我叫<PERSON_1>，手机号<PHONE_1>",
        )
        self.assertEqual(response.choices[0].message.content, "已记录 张三 的手机号 13812345678")

    async def test_unmasks_async_chat_stream(self):
        client = FakeAsyncClient()
        wrapped = ShieldedAsyncOpenAI(client=client)

        stream = await wrapped.chat.completions.create(
            model="fake-model",
            messages=[{"role": "user", "content": "我是李四，手机号13900001111"}],
            stream=True,
        )

        chunks = []
        async for event in stream:
            chunks.append(event.choices[0].message.content)

        self.assertEqual(chunks, ["已记录 李四", " 的手机号 13900001111"])

    async def test_masks_async_responses_api_and_unmasks_output(self):
        client = FakeAsyncClient()
        wrapped = ShieldedAsyncOpenAI(client=client)

        response = await wrapped.responses.create(
            model="fake-model",
            input="我叫张三，手机号13812345678",
        )

        self.assertEqual(client.responses.last_input, "我叫<PERSON_1>，手机号<PHONE_1>")
        self.assertEqual(response.output_text, "你好 张三，手机号 13812345678 已收到")

    async def test_unmasks_async_responses_stream(self):
        client = FakeAsyncClient()
        wrapped = ShieldedAsyncOpenAI(client=client)

        stream = await wrapped.responses.create(
            model="fake-model",
            input="我叫张三，手机号13812345678",
            stream=True,
        )

        chunks = []
        async for event in stream:
            chunks.append(event["output_text"])

        self.assertEqual(chunks, ["你好 张三", "，手机号 13812345678 已收到"])


if __name__ == "__main__":
    unittest.main()
