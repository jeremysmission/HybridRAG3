from openai import AzureOpenAI
import keyring
c = AzureOpenAI(
    azure_endpoint=keyring.get_password('hybridrag','api_endpoint'),
    api_key=keyring.get_password('hybridrag','api_key'),
    api_version='2024-02-02'
)
r = c.chat.completions.create(
    model='gpt-35-turbo',
    messages=[{'role':'user','content':'say hello'}]
)
print(r.choices[0].message.content)