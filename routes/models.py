from fastapi import FastAPI
from collections import defaultdict

def create_model_routes(app: FastAPI, providers: dict):
    @app.get("/v1/models")
    async def get_models():
        model_data = defaultdict(lambda: {"providers": [], "costs": []})
        
        for provider_name, provider in providers.items():
            for model_name in provider.models:
                credit_cost = provider.costs.get(model_name, 1)
                model_data[model_name]["providers"].append(provider_name)
                model_data[model_name]["costs"].append(credit_cost)
        
        model_list = []
        for model_name, data in model_data.items():
            providers_list = data["providers"]
            costs = data["costs"]
            
            min_cost = min(costs)
            
            model_list.append({
                "id": model_name,
                "name": ''.join(c.lower() if i > 0 and c.isupper() and model_name[i-1].isdigit() else c for i, c in enumerate(model_name.replace("-", " ").title().replace("Gpt", "GPT"))),
                "object": "model",
                "created": 0,
                "owned_by": providers_list[0] if len(providers_list) == 1 else providers_list,
                "parent": None,
                "root": None,
                "permission": {
                    "allow_create_engine": True,
                    "allow_sampling": True,
                    "allow_logprobs": True,
                    "allow_search_indices": True,
                    "allow_view": True,
                    "allow_fine_tuning": True,
                    "organization": "*",
                    "is_blocking": False
                },
                "cost": min_cost
            })
        return {"data": model_list}
