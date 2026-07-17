import os
from openai import OpenAI
import anthropic
import google.generativeai as genai

class Openai_api:
    def __init__(self, api_key, model):

        # Allow routing through OpenAI-compatible endpoints (e.g. OpenRouter) via env vars.
        # OPENAI_BASE_URL=https://openrouter.ai/api/v1
        # DEEPRARE_MINI_MODEL=<id used for "mini" summarisation calls>
        base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENROUTER_BASE_URL")
        kwargs = {"api_key": api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model
        # Per-class fallback for the "mini" summariser model id. Defaults to gpt-4o-mini,
        # but on OpenRouter we need a routable id like 'openai/gpt-4o-mini' or
        # 'google/gemini-3-flash-preview'. Use env override.
        self.mini_model = os.environ.get("DEEPRARE_MINI_MODEL") or "gpt-4o-mini"

        self.gpt4_tokens = 0
        self.chatgpt_tokens = 0
        self.gpt_4o_mini_tokens = 0

    def get_completion(self, system_prompt, prompt, seed=42):
        try:
            # 2026-05-19 — propagate OPENROUTER_REASONING_EFFORT for GPT-5 /
            # o-series. openai>=1 supports `extra_body` to pass provider-
            # specific fields through verbatim; OpenRouter accepts
            # `reasoning: {effort: ...}`.
            _kwargs = {}
            _reasoning = os.environ.get("OPENROUTER_REASONING_EFFORT")
            if _reasoning:
                _kwargs["extra_body"] = {"reasoning": {"effort": _reasoning}}
            completion = self.client.chat.completions.create(
                model=self.model,
                seed=seed,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                **_kwargs,
            )

            return str(completion.choices[0].message.content)
        except Exception as e:
            print(e)
            return None

    def openai_summarize(self, text: str):
        try:
            output = self.get_completion("Assume you are a doctor, please summarize these medical article into a paragraph, only keep key message, mainly focus on the phenotype and related disease.",
                                        text)
            if 'not a medical-related page' in output.lower():
                return ""
            else:
                return output
        except:
            print("Error in summarizing the text. Return the first 1000 characters.")
            return text[:1000]

    def mini_completion(self, system_prompt, prompt, seed=42):
        try:
            # 2026-05-19 — see get_completion above; same reasoning_effort propagation.
            _kwargs = {}
            _reasoning = os.environ.get("OPENROUTER_REASONING_EFFORT")
            if _reasoning:
                _kwargs["extra_body"] = {"reasoning": {"effort": _reasoning}}
            completion = self.client.chat.completions.create(
                model=self.mini_model,
                seed=seed,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                **_kwargs,
            )

            return str(completion.choices[0].message.content)
        except Exception as e:
            print(e)
            return None

    def get_embedding(self, text: str, model="text-embedding-3-small") -> list[float]:
        # OpenRouter does NOT expose an embeddings endpoint in v1. If the OpenAI client
        # is pointed at OpenRouter, embedding requests will fail. Three options:
        #   1) DEEPRARE_DISABLE_EMBEDDING=1 -> return zero vector (semantic search disabled)
        #   2) DEEPRARE_LOCAL_EMBEDDING=1   -> use a local SentenceTransformer
        #      (default model: BAAI/bge-small-en-v1.5, 384-dim, ~110 MB)
        #   3) (default) call the configured embeddings endpoint
        #
        # Note: similar_case_search compares to per-row stored embeddings in
        # RDS_embeddings.csv (1536-dim text-embedding-3-small vectors). Local
        # 384-dim vectors won't be directly comparable to those — we pad with
        # zeros to 1536 so cosine_similarity doesn't crash on shape mismatch.
        # The resulting ranking is effectively random / row-order biased, which
        # is acceptable for a smoke test (similar_case_search returns top-N).
        if os.environ.get("DEEPRARE_LOCAL_EMBEDDING") == "1":
            global _DEEPRARE_LOCAL_EMBEDDER
            try:
                _DEEPRARE_LOCAL_EMBEDDER
            except NameError:
                _DEEPRARE_LOCAL_EMBEDDER = None
            if _DEEPRARE_LOCAL_EMBEDDER is None:
                from sentence_transformers import SentenceTransformer
                model_name = os.environ.get("DEEPRARE_LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
                _DEEPRARE_LOCAL_EMBEDDER = SentenceTransformer(model_name)
            vec = _DEEPRARE_LOCAL_EMBEDDER.encode(text, normalize_embeddings=True).tolist()
            target_dim = 1536
            if len(vec) < target_dim:
                vec = vec + [0.0] * (target_dim - len(vec))
            elif len(vec) > target_dim:
                vec = vec[:target_dim]
            return vec
        if os.environ.get("DEEPRARE_DISABLE_EMBEDDING") == "1":
            # 1536-dim zero vector ~ text-embedding-3-small dim. Effectively disables
            # similar-case ranking while keeping downstream code happy.
            return [0.0] * 1536
        return self.client.embeddings.create(input=[text], model=model).data[0].embedding

class deepseek_api:
    def __init__(self, api_key, model):

        self.client = OpenAI(
                api_key=api_key, 
                base_url="https://api.deepseek.com",
                )
        if model == 'deepseek-v3-241226':
            self.model = "deepseek-chat"
        elif model == 'deepseek-r1-250120':
            self.model = "deepseek-reasoner"
        
    def get_completion(self, system_prompt, prompt, seed=42):
        try:       
            print("deepseek model: ", self.model)
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                stream=False
            )
            
            return str(completion.choices[0].message.content)
        except Exception as e:
            print(e)
            return None

class gemini_api:
    def __init__(self, api_key, model):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

    def get_completion(self, system_prompt, prompt, seed=42):
        try:       
            # Combine system prompt and user prompt
            full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
            response = self.model.generate_content(full_prompt)
            return str(response.text)
        except Exception as e:
            print(e)
            return None

class claude_api:
    def __init__(self, api_key, model):
        self.client = anthropic.Anthropic(
            api_key=api_key
        )
        self.model = model
        
    def get_completion(self, system_prompt, prompt, seed=42):
        try:       
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return str(message.content[0].text)
        except Exception as e:
            print(e)
            return None