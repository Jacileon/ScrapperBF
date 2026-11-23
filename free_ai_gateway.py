# -*- coding: utf-8 -*-
"""
Passerelle Universelle Multi-Fournisseurs Gratuits (Free AI Gateway).
Permet d'utiliser en toute transparence :
- DeepSeek Web Free (via session locale)
- Groq Cloud Free (Llama 3.3 70B Versatile, Mixtral 8x7B)
- Google Gemini Free (Gemini 1.5 Flash, Gemini 2.0 Flash)
- Z.ai (GLM-5.3-flash)

Chaque requête peut cibler un fournisseur précis ou utiliser le mode AUTO (failover automatique).
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

class FreeAIGateway:
    def __init__(self, config_path: Optional[str] = None):
        self.config = {
            "deepseek_local_url": "http://127.0.0.1:8000/v1/chat/completions",
            "groq_api_key": os.getenv("GROQ_API_KEY", ""),
            "groq_url": "https://api.groq.com/openai/v1/chat/completions",
            "groq_default_model": "llama-3.3-70b-versatile",
            "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
            "gemini_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "gemini_default_model": "gemini-1.5-flash",
            "zai_api_key": os.getenv("ZAI_API_KEY", "2d1556e2fee64e81b14cd86fb3de2217.GVbPpvlw9YgedJ2X"),
            "zai_url": "https://api.z.ai/api/paas/v4/chat/completions",
            "zai_default_model": "glm-5.3-flash",
        }
        if config_path and os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self.config.update(json.load(f))

    def chat(self, prompt: str, system_prompt: Optional[str] = None, provider: str = "auto", model: Optional[str] = None) -> Dict[str, Any]:
        """
        Envoie un prompt vers le fournisseur choisi ou bascule automatiquement (auto-failover).
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        providers_order = [provider] if provider != "auto" else ["deepseek", "groq", "gemini", "zai"]
        errors = {}

        for p in providers_order:
            try:
                if p == "deepseek":
                    res = self._call_deepseek_local(messages, model)
                    return {"success": True, "provider": "deepseek", "content": res}
                elif p == "groq" and self.config.get("groq_api_key"):
                    res = self._call_groq(messages, model)
                    return {"success": True, "provider": "groq", "content": res}
                elif p == "gemini" and self.config.get("gemini_api_key"):
                    res = self._call_gemini(messages, model)
                    return {"success": True, "provider": "gemini", "content": res}
                elif p == "zai":
                    res = self._call_zai(messages, model)
                    return {"success": True, "provider": "zai", "content": res}
            except Exception as e:
                errors[p] = str(e)

        return {"success": False, "errors": errors}

    def _call_deepseek_local(self, messages, model=None):
        data = {
            "model": model or "deepseek-chat",
            "messages": messages,
            "temperature": 0.1
        }
        req = urllib.request.Request(
            self.config["deepseek_local_url"],
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            return out["choices"][0]["message"]["content"]

    def _call_groq(self, messages, model=None):
        data = {
            "model": model or self.config["groq_default_model"],
            "messages": messages,
            "temperature": 0.1
        }
        req = urllib.request.Request(
            self.config["groq_url"],
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config['groq_api_key']}"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            return out["choices"][0]["message"]["content"]

    def _call_gemini(self, messages, model=None):
        data = {
            "model": model or self.config["gemini_default_model"],
            "messages": messages,
            "temperature": 0.1
        }
        req = urllib.request.Request(
            self.config["gemini_url"],
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config['gemini_api_key']}"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            return out["choices"][0]["message"]["content"]

    def _call_zai(self, messages, model=None):
        data = {
            "model": model or self.config["zai_default_model"],
            "messages": messages,
            "temperature": 0.1
        }
        req = urllib.request.Request(
            self.config["zai_url"],
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config['zai_api_key']}"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode("utf-8"))
            return out["choices"][0]["message"]["content"]

if __name__ == "__main__":
    gw = FreeAIGateway()
    print("Passerelle FreeAIGateway prête !")
    print("Fournisseurs configurés : DeepSeek Local, Groq, Google Gemini, Z.ai")
