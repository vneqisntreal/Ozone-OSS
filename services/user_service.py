from typing import Optional, Dict, Any
from utils.logger import user_logger
import time
import json
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from config import MONGODB_URI

class DatabaseError(Exception):
    pass

class UserNotFoundError(DatabaseError):
    pass

with open("data/plans.json", "r") as f:
    plans = json.loads(f.read())

class UserService:
    def __init__(self, mongodb_url: str = MONGODB_URI):
        try:
            self.client = MongoClient(mongodb_url)
            self.db = self.client.ozone_db
            self.users = self.db.users
        except PyMongoError as e:
            user_logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise DatabaseError(f"MongoDB connection error: {str(e)}")

    def get_user_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            result = self.users.find_one({"discord_id": user_id})
            if not result:
                return None

            current_time = time.time()
            time_since_reset = current_time - (result.get('last_reset', 0) or 0)

            return {
                "api_key": result.get('_id'), 
                "current_tokens": result.get('current_tokens', 0),
                "last_reset": result.get('last_reset'),
                "daily_token_limit": result.get('daily_token_limit'),
                "daily_token_expiration": result.get('daily_token_expiration'),
                "plan_expiration": result.get('plan_expiration'),
                "reset_available": time_since_reset >= 86400,
                "time_since_reset": time_since_reset,
                "plan": result.get('plan', 'default') 
            }
        except PyMongoError as e:
            raise DatabaseError(f"Error fetching user data: {str(e)}")
            
    def update_tokens(self, user_id: str, token_change: int) -> None:
        try:
            result = self.users.find_one_and_update(
                {"_id": user_id},
                {"$inc": {"current_tokens": token_change}},
                return_document=True
            )
            
            if not result:
                raise UserNotFoundError(f"User {user_id} not found")


        except PyMongoError as e:
            raise DatabaseError(f"Error updating tokens: {str(e)}")

    def create_user(self, api_key: str, user_data: Dict[str, Any]) -> None:

        try:
            document = {
                "_id": api_key,
                "current_tokens": user_data.get("daily_token_limit", 0),
                "tokens": user_data.get('tokens', 0),
                "last_reset": user_data.get('last_reset', time.time()),
                "plan": user_data.get('plan', 'default'),
                "daily_token_limit": user_data.get('daily_token_limit', 0),
                "discord_id": user_data.get('discord_id')
            }
            
            if "plan" in user_data and user_data["plan"] in plans:
                document["current_tokens"] = plans[user_data["plan"]]["tokens_per_day"]
            else:
                document["current_tokens"] = 0

            
            result = self.users.insert_one(document)
            
            if not result.acknowledged:
                raise DatabaseError("Failed to create new user")
                
            
        except PyMongoError as e:
            raise DatabaseError(f"Error creating user: {str(e)}")

    def change_plan(self, api_key: str, plan_name: str, expiration_time: float) -> None:
        try:
          update_data = {
              "$set": {
                "plan": plan_name,
                  "plan_expiration": expiration_time
              }
          }
          
          if plan_name in plans:
            update_data["$set"]["current_tokens"] = plans[plan_name]["tokens_per_day"]
          
          result = self.users.find_one_and_update(
                {"_id": api_key},
                update_data,
                return_document=True
            )

          if not result:
              raise UserNotFoundError(f"User {api_key} not found")
              

        except PyMongoError as e:
          raise DatabaseError(f"Error updating user plan: {str(e)}")
    
    def get_user_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:

        try:
            result = self.users.find_one({"_id": api_key})
            if not result:
                return None

            current_time = time.time()
            time_since_reset = current_time - (result.get('last_reset', 0) or 0)


            return {
                "api_key": result.get('_id'), 
                "current_tokens": result.get('current_tokens', 0),
                "last_reset": result.get('last_reset'),
                "daily_token_limit": result.get('daily_token_limit'),
                "daily_token_expiration": result.get('daily_token_expiration'),
                "plan_expiration": result.get('plan_expiration'),
                "reset_available": time_since_reset >= 86400,
                "time_since_reset": time_since_reset,
                "plan": result.get('plan', 'default')  
            }
            print(result)
            return result
        except PyMongoError as e:
            raise DatabaseError(f"Error fetching user by API key: {str(e)}")
            
    def regenerate_api_key(self, discord_id: str, new_api_key: str) -> Optional[int]:
        try:
            user = self.users.find_one({"discord_id": discord_id})
            if not user:
                return None

            current_tokens = user.get('tokens')
            
            result = self.users.find_one_and_update(
                {"discord_id": discord_id},
                {"$set": {"_id": new_api_key}},
                return_document=True
            )

            if not result:
                return None
            

            return current_tokens

        except PyMongoError as e:
            raise DatabaseError(f"Error regenerating API key: {str(e)}")

    def delete_user(self, discord_id: str) -> Optional[str]:
        try:
            user = self.users.find_one({"discord_id": discord_id})
            if not user:
                return None

            api_key = user.get('_id')
            result = self.users.delete_one({"discord_id": discord_id})

            if result.deleted_count == 0:
                return None

            return api_key

        except PyMongoError as e:
            raise DatabaseError(f"Error deleting user: {str(e)}")