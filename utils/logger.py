import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logger(name, log_file='api.log', level=logging.INFO):
	logger = logging.getLogger(name)
	logger.setLevel(level)
	
	formatter = logging.Formatter(
		'%(asctime)s - %(name)s - %(levelname)s - %(message)s'
	)
	
	console_handler = logging.StreamHandler(sys.stdout)
	console_handler.setFormatter(formatter)
	logger.addHandler(console_handler)
	
	if not os.path.exists('logs'):
		os.makedirs('logs')
	file_handler = RotatingFileHandler(
		f'logs/{log_file}',
		maxBytes=10*1024*1024,
		backupCount=5
	)
	file_handler.setFormatter(formatter)
	logger.addHandler(file_handler)
	
	return logger

chat_logger = setup_logger('chat_service', 'chat.log')
user_logger = setup_logger('user_service', 'user.log')
provider_logger = setup_logger('provider_service', 'provider.log')

__all__ = ['chat_logger', 'user_logger', 'provider_logger', 'setup_logger']