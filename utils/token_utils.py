import time

def calculate_tokens(input_length, output_length, model_multiplier):
    input_tokens = input_length / 4
    output_tokens = output_length / 3
    
    base_tokens = input_tokens + output_tokens
    
    total_tokens = base_tokens * model_multiplier
    
    total_tokens = total_tokens * 1.05
    
    return total_tokens

