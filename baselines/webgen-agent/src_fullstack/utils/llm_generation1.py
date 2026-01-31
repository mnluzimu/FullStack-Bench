import os
import openai
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

import sys
project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from prompts.system import system_prompt

client = OpenAI(api_key=os.environ["OPENAILIKE_API_KEY"], 
                base_url=os.environ["OPENAILIKE_BASE_URL"])


def llm_generation(messages, model):
    chat_response = client.chat.completions.create(
        model=model,
        messages=messages
    )

    return chat_response.choices[0].message.content