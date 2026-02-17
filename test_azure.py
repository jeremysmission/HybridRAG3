# ============================================================================
# HybridRAG v3 - Quick Azure API Test (test_azure.py)
# ============================================================================
#
# WHAT THIS FILE DOES:
#   Sends a single "say hello" message to Azure OpenAI to verify that
#   credentials, endpoint, and network connectivity all work.
#
# KEYRING SCHEMA:
#   service:  "hybridrag"
#   key name: "azure_api_key"     (the API key itself)
#   key name: "azure_endpoint"    (the https://...openai.azure.com URL)
#
# IMPORTANT: These key names MUST match what credentials.py uses.
#   Previously this file used "api_key" and "api_endpoint" which are
#   WRONG and would return None even when credentials are stored.
#
# INTERNET ACCESS: YES - sends one API request to Azure
# ============================================================================

from openai import AzureOpenAI
import keyring

c = AzureOpenAI(
    azure_endpoint=keyring.get_password('hybridrag', 'azure_endpoint'),
    api_key=keyring.get_password('hybridrag', 'azure_api_key'),
    api_version='2024-02-02'
)
r = c.chat.completions.create(
    model='gpt-35-turbo',
    messages=[{'role': 'user', 'content': 'say hello'}]
)
print(r.choices[0].message.content)
