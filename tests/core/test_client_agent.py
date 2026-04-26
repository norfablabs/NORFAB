class TestClientApi:
    def test_get_agent(self, nfclient):
        agent = nfclient.get_agent(profile="default")

        answer = agent.invoke("Tell me who you are in 5 words")
        print(f"AGENT ANSWER: '{answer}'")

        assert answer and isinstance(answer, str), f"Unexpected answer: '{answer}'"
