import pprint
import json
import time
import pytest
from uuid import uuid4
from norfab.core.client import JobStatus


class TestClientApi:
    def test_get_agent(self, nfclient):
        agent = nfclient.get_agent(profile="default")

        answer = agent.invoke("Tell me who you are in 5 words")
        print(f"AGENT ANSWER: '{answer}'")
        
        assert answer and isinstance(answer, str), f"Unexpected answer: '{answer}'"