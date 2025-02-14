import sqlite3
import time
import json
import logging

def init_db():
    conn = sqlite3.connect('user_keys.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            api_key TEXT NOT NULL,
            tokens INTEGER DEFAULT 90000,
            last_reset REAL
        )
    ''')
    
    columns_to_add = [
        ('plan', 'TEXT DEFAULT "default"'),
        ('plan_expiration', 'REAL'),
        ('daily_token_limit', 'INTEGER'),
        ('daily_token_expiration', 'REAL')
    ]
    
    for column_name, column_type in columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {column_name} {column_type}')
        except sqlite3.OperationalError:
            pass
    
    conn.commit()
    conn.close()

def load_plans():
    with open('data/plans.json') as f:
        return json.load(f)

plans = load_plans()

def add_user(api_key, plan='default', plan_expiration=None):
    if plan not in plans:
        plan = 'default'
    
    conn = sqlite3.connect('user_keys.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO users (
            id, 
            api_key, 
            tokens, 
            last_reset, 
            plan, 
            plan_expiration, 
            daily_token_limit, 
            daily_token_expiration
        ) VALUES (
            :id,
            :api_key,
            :tokens,
            :last_reset,
            :plan,
            :plan_expiration,
            :daily_token_limit,
            :daily_token_expiration
        )
    ''', {
        'id': api_key,
        'api_key': api_key,
        'tokens': plans[plan]['tokens_per_day'],
        'last_reset': time.time(),
        'plan': plan,
        'plan_expiration': plan_expiration if plan_expiration is not None else None,
        'daily_token_limit': plans[plan]['tokens_per_day'],
        'daily_token_expiration': None
    })
    
    conn.commit()
    conn.close()

def update_user_plan(api_key, plan, plan_expiration):
    if plan not in plans:
        plan = 'default'
        
    conn = sqlite3.connect('user_keys.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users
        SET plan = :plan,
            plan_expiration = :plan_expiration,
            daily_token_limit = :daily_token_limit,
            tokens = :tokens
        WHERE api_key = :api_key
    ''', {
        'plan': plan,
        'plan_expiration': plan_expiration,
        'daily_token_limit': plans[plan]['tokens_per_day'],
        'tokens': plans[plan]['tokens_per_day'],
        'api_key': api_key
    })
    
    conn.commit()
    conn.close()

def get_user(api_key):
    conn = sqlite3.connect('user_keys.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, api_key, tokens, plan, plan_expiration, daily_token_limit, daily_token_expiration FROM users WHERE api_key = ?', (api_key,))
    user = cursor.fetchone()
    result = None
    if user:
        columns = [column[0] for column in cursor.description]
        user_dict = dict(zip(columns, user))
        
        user_dict['plan'] = user_dict.get('plan') if user_dict.get('plan') in plans else 'default'
        plan = plans[user_dict['plan']]
        
        user_dict['tokens'] = user_dict.get('tokens', plan['tokens_per_day'])
        user_dict['plan_expiration'] = user_dict.get('plan_expiration')  # Can be None
        user_dict['daily_token_limit'] = user_dict.get('daily_token_limit', plan['tokens_per_day'])
        user_dict['daily_token_expiration'] = user_dict.get('daily_token_expiration')  # Can be None
        
        result = user_dict
    conn.close()
    return result

def update_tokens(api_key, tokens, period='minute'):
    conn = sqlite3.connect('user_keys.db')
    cursor = conn.cursor()
    
    try:
        user = get_user(api_key)
        if not user:
            raise ValueError(f"User with API key {api_key} not found")
            
        current_tokens = user['tokens']
        
        new_tokens = current_tokens + tokens
        if new_tokens < 0:
            new_tokens = 0
        
        cursor.execute('''
            UPDATE users
            SET tokens = ?
            WHERE api_key = ?
        ''', (new_tokens, api_key))
        conn.commit()
        
        return new_tokens
        
    except Exception as e:
        logging.error(f"Error updating tokens: {e}")
        raise
    
    finally:
        conn.close()

def reset_period_tokens(period='minute'):
    try:
        conn = sqlite3.connect('user_keys.db')
        cursor = conn.cursor()
        current_time = time.time()

        # Handle period-based resets
        if period == 'minute':
            interval = 60
        elif period == 'hour':
            interval = 3600
        else:
            interval = 86400

        cursor.execute('SELECT id, last_reset, plan FROM users')
        users = cursor.fetchall()
        
        for user_id, last_reset, user_plan in users:
            try:
                if user_plan not in plans:
                    user_plan = 'default'
                plan = plans[user_plan]
                
                if last_reset is None or current_time >= last_reset + interval:
                    cursor.execute('''
                        UPDATE users 
                        SET tokens = ?, 
                            last_reset = ? 
                        WHERE id = ?
                    ''', (plan['tokens_per_day'], current_time, user_id))
            except Exception as e:
                logging.error(f"Error resetting tokens for user {user_id}: {e}")
                continue
        
        conn.commit()
        
        cursor.execute('SELECT id, daily_token_limit, daily_token_expiration FROM users')
        users = cursor.fetchall()
        
        for user_id, daily_token_limit, daily_token_expiration in users:
            try:
                if daily_token_limit is not None and (daily_token_expiration is None or current_time >= daily_token_expiration):
                    cursor.execute('''
                        UPDATE users 
                        SET tokens = ?,
                            daily_token_limit = ?,
                            daily_token_expiration = NULL 
                        WHERE id = ?
                    ''', (daily_token_limit, daily_token_limit, user_id))
            except Exception as e:
                logging.error(f"Error resetting daily tokens for user {user_id}: {e}")
                continue
        
        conn.commit()
        
    except Exception as e:
        logging.error(f"Error in reset_period_tokens: {e}")
        raise
        
    finally:
        conn.close()

init_db()
