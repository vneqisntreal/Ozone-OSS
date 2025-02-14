import discord
from discord.ext import commands
from discord.app_commands import Choice
import random
import time
import aiohttp
from config import DISCORD_TOKEN
from discord import app_commands
from services.user_service import UserService, UserNotFoundError, DatabaseError
import asyncio 
import subprocess

intents = discord.Intents.default()
intents.message_content = True  
bot = commands.Bot(command_prefix='!', intents=intents)
user_service = UserService()  

channel_model_mapping = {
    1336343549536374796: "claude-3-5-sonnet-20240612",
    1336343683510829130: "claude-3-5-sonnet-20241022",
    1336343572412239952: "gpt-4o",
    1336343612891467907: "gpt-3.5-turbo",
    1336343779011203223: "o3-mini",
    1336343819238637619: "o1-mini",
    1336343752955924580: "shuttle-3",
    1336343768579969116: "s1-mini",
    1336343733670645831: "fluffy-chat"
}

async def send_chunked_response(message, response):
    chunk_size = 1000
    chunks = [response[i:i + chunk_size] for i in range(0, len(response), chunk_size)]
    
    for chunk in chunks:
        await message.reply(chunk)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.id in channel_model_mapping:
        model = channel_model_mapping[message.channel.id]
        
        processing_message = await message.reply("Model is generating its response...")
        
        try:
            user_data = user_service.get_user_data(str(message.author.id))
            
            if not user_data:
                await processing_message.edit(content="Error: No API key found. Use `/manage` to generate a new key.")
                return
            
            api_key = user_data['api_key']
            start_time = time.time()
            response_data = await make_api_request(api_key, model, message.content)
            
            await processing_message.delete()
            
            if 'choices' in response_data and len(response_data['choices']) > 0:
                answer = response_data['choices'][0]['message']['content']
                await send_chunked_response(message, answer)
            else:
                await message.channel.send(embed=create_embed("Error", "Failed to get a valid response from the API."))
        
        except Exception as e:
            await processing_message.edit(content=f"Error: {str(e)}")

    await bot.process_commands(message)  

async def make_api_request(api_key, model, prompt):
    url = "https://api.ozone-ai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            return await response.json()


def has_admin_role():
    async def predicate(interaction: discord.Interaction):
        return any(role.id == 1324195577558335619 for role in interaction.user.roles)
    return discord.app_commands.check(predicate)

class ConfirmationView(discord.ui.View):
    def __init__(self, user_discord_id: str):
        super().__init__(timeout=180)
        self.user_discord_id = user_discord_id

    @discord.ui.button(label='Reset Credits', style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await reset_tokens_internal(interaction, self.user_discord_id)
        
async def reset_tokens_internal(interaction: discord.Interaction, user_discord_id: str):
    try:
        user_data = user_service.get_user_data(user_discord_id)
        if not user_data:
            await interaction.response.send_message(embed=create_embed("Error", "User not found."), ephemeral=True)
            return
            
        if time.time() - user_data['last_reset'] >= 86400:
            user_plan = user_data.get('plan', 'default')
            token_limit = plans[user_plan]['tokens_per_day']
            api_key = user_data['api_key']
            user_service.update_tokens(api_key, token_limit - user_data['current_tokens'])
            user_service.users.find_one_and_update(
                {"discord_id": user_discord_id},
                {"$set": {"last_reset": time.time()}}
            )  
            await interaction.response.send_message(embed=create_embed("Credits Reset", "Credits reset successfully."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=create_embed("Error", "You can only reset credits once every 24 hours."), ephemeral=True)
    except DatabaseError as e:
        await interaction.response.send_message(embed=create_embed("Error", str(e)), ephemeral=True)


def create_embed(title, description, color=discord.Color.blue(), footer=None):
    embed = discord.Embed(title=title, description=description, color=color)
    if footer:
        embed.set_footer(text=footer)
    else:
        embed.set_footer(text="Ozone API, the best free OpenAI reverse proxy.")
    return embed

@bot.tree.command(name='manage')
async def manage(interaction: discord.Interaction):
    discord_id = str(interaction.user.id)
    try:
        user_data = user_service.get_user_data(discord_id)
        
        if user_data:
            current_key = user_data['api_key']
            last_reset = user_data['last_reset']
            user_plan = user_data.get('plan', 'default')
            reset_available = time.time() - last_reset >= 86400

            token_amount = plans[user_plan]['tokens_per_day']

            view = ConfirmationView(discord_id) if reset_available else None

            await interaction.response.send_message(embeds=[
                create_embed("Your API Key", 
                    f"Your API key: \n```{current_key}```\nPlease don't share this with anyone.", 
                    discord.Color.green()),
                create_embed("Credit Balance", 
                    f"Your current balance:\n```${user_data['current_tokens']}```\nUse your money wisely!", 
                    discord.Color.orange())
            ], view=view, ephemeral=True)
        else:
            new_key = "sk-ozone-" + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=45))
            default_plan = 'default'
            
            user_service.create_user(new_key, {
                'tokens': plans[default_plan]['tokens_per_day'],
                'last_reset': time.time(),
                'plan': default_plan,
                'daily_token_limit': plans[default_plan]['tokens_per_day'],
                'discord_id': discord_id
            })
            
            await interaction.response.send_message(embeds=[
                create_embed("New API Key Generated", 
                    f"New API key: ```{new_key}```\nPlease don't share this with anyone.", 
                    discord.Color.green()),
                create_embed("Credit Balance", 
                    f"Your current balance: \n```${plans[default_plan]['tokens_per_day']}```\nUse it wisely!", 
                    discord.Color.orange())
            ], ephemeral=True)
    except DatabaseError as e:
        await interaction.response.send_message(embed=create_embed("Error", str(e)), ephemeral=True)

@bot.tree.command(name='ask')
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.user_install()
@app_commands.choices(models=[
    Choice(name='GPT 4o Mini', value="gpt-4o-mini"),
    Choice(name='GPT 4o', value="gpt-4o"),
    Choice(name='o1 Mini', value="o1-mini"),
])
async def ask(
    interaction: discord.Interaction,
    prompt: str,
    models: Choice[str]
):
    discord_id = str(interaction.user.id)
    try:
        user_data = user_service.get_user_data(discord_id)
        
        if user_data:
            api_key = user_data['api_key']
            start_time = time.time()
            response_data = await make_api_request(api_key, models.value, prompt)
            end_time = time.time()
            
            if 'choices' in response_data and len(response_data['choices']) > 0:
                answer = response_data['choices'][0]['message']['content']
                time_taken = f"Time taken: {end_time - start_time:.2f} seconds"
                await interaction.response.send_message(
                    embed=create_embed("Response", answer, discord.Color.blurple(), footer=time_taken), 
                    ephemeral=False
                )
            else:
                await interaction.response.send_message(
                    embed=create_embed("Error", "Failed to get a valid response from the API."), 
                    ephemeral=False
                )
        else:
            await interaction.response.send_message(
                embed=create_embed("Error", "No API key found. Use `/manage` to generate a new key."), 
                ephemeral=False
            )
    except DatabaseError as e:
        await interaction.response.send_message(
            embed=create_embed("Error", str(e)), 
            ephemeral=False
        )

@bot.tree.command(name='regeneratekey')
async def regenerate_key(interaction: discord.Interaction):
    discord_id = str(interaction.user.id)
    try:
        new_key = "sk-ozone-" + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=45))
        current_tokens = user_service.regenerate_api_key(discord_id, new_key)
        
        if current_tokens is not None:
            await interaction.response.send_message(
                embed=create_embed("API Key Regenerated", 
                f"Your new API key: ```{new_key}```\n Balance remains: `${current_tokens}`"), 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=create_embed("Error", "No API key found. Use `/manage` to generate a new key."), 
                ephemeral=True
            )
    except DatabaseError as e:
        await interaction.response.send_message(
            embed=create_embed("Error", str(e)), 
            ephemeral=True
        )


@bot.tree.command(name='resetbalance')
@has_admin_role()
async def reset_tokens(interaction: discord.Interaction, api_key: str):
    try:
        user_service.update_tokens(api_key, 90000)
        await interaction.response.send_message(
            embed=create_embed("Balance Reset", "Balance reset successfully."), 
            ephemeral=True
        )
    except DatabaseError as e:
        await interaction.response.send_message(
            embed=create_embed("Error", str(e)), 
            ephemeral=True
        )

@bot.tree.command(name='reset_all_tokens')
@has_admin_role()
async def reset_all_tokens(interaction: discord.Interaction):
    try:
        all_users = user_service.users.find()
        for user in all_users:
            user_plan = user.get('plan', 'default')
            token_limit = plans[user_plan]['tokens_per_day']
            api_key = user['_id']
            user_service.update_tokens(api_key, token_limit - user['current_tokens'])
            user_service.users.find_one_and_update(
                {"_id": api_key},
                {"$set": {"last_reset": time.time()}}
            )
        await interaction.response.send_message(
            embed=create_embed("Tokens Reset", "All users' tokens have been reset to their plan default."),
            ephemeral=True
        )
    except DatabaseError as e:
        await interaction.response.send_message(
            embed=create_embed("Error", str(e)),
            ephemeral=True
        )

@has_admin_role()
async def change_tokens(interaction: discord.Interaction, api_key: str, tokens: int):
    try:
        user_service.update_tokens(api_key, tokens - user_service.get_user_data(api_key)['current_tokens'])
        await interaction.response.send_message(
            embed=create_embed("Balance Changed", f"Balance changed to `{tokens}` for API key `{api_key}`."), 
            ephemeral=True
        )
    except UserNotFoundError:
        await interaction.response.send_message(
            embed=create_embed("Error", f"No user found with API key `{api_key}`."), 
            ephemeral=True
        )
    except DatabaseError as e:
        await interaction.response.send_message(
            embed=create_embed("Error", str(e)), 
            ephemeral=True
        )


@bot.tree.command(name='change_plan')
@has_admin_role()
async def change_plan(interaction: discord.Interaction, api_key: str, plan_name: str, expiration_days: int = 30):
    if plan_name not in plans:
        await interaction.response.send_message(embed=create_embed("Error", f"Plan `{plan_name}` does not exist."), ephemeral=True)
        return

    try:
        expiration_time = time.time() + (expiration_days * 86400)
        user_service.change_plan(api_key, plan_name, expiration_time)
        await interaction.response.send_message(embed=create_embed("Plan Changed", f"Plan for API key `{api_key}` changed to `{plan_name}`. Expires in `{expiration_days}` days."), ephemeral=True)
    except UserNotFoundError:
        await interaction.response.send_message(embed=create_embed("Error", f"No user found with API key `{api_key}`."), ephemeral=True)
    except DatabaseError as e:
        await interaction.response.send_message(embed=create_embed("Error", str(e)), ephemeral=True)

@bot.tree.command(name='get_key')
@has_admin_role()
async def get_key(interaction: discord.Interaction, user: discord.Member):
    try:
        api_key = user_service.get_user_data(str(user.id))
        if api_key:
            await interaction.response.send_message(
                embed=create_embed("User's API Key", 
                f"API key for {user.mention}: ```{api_key}```"),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=create_embed("Error", f"No API key found for {user.mention}."),
                ephemeral=True
            )
    except DatabaseError as e:
        await interaction.response.send_message(
            embed=create_embed("Error", str(e)), 
            ephemeral=True
        )


@bot.tree.command(name='add_key')
@has_admin_role()
async def add_key(interaction: discord.Interaction, user: discord.Member, api_key: str, plan_name: str = 'default', expiration_days: int = 30):
    if plan_name not in plans:
      await interaction.response.send_message(embed=create_embed("Error", f"Plan `{plan_name}` does not exist."), ephemeral=True)
      return
      
    discord_id = str(user.id)
    conn = sqlite3.connect('user_keys.db')
    try:
      cursor = conn.cursor()

      cursor.execute('SELECT id FROM users WHERE id = ?', (api_key,))
      if cursor.fetchone():
          await interaction.response.send_message(embed=create_embed("Error", f"API key `{api_key}` already exists in the database."), ephemeral=True)
          return

      cursor.execute('SELECT api_key FROM discord_to_api WHERE discord_id = ?', (discord_id,))
      if cursor.fetchone():
          await interaction.response.send_message(embed=create_embed("Error", f"User {user.mention} already has an API key. Use `/delete_key` first."), ephemeral=True)
          return

      expiration_time = time.time() + (expiration_days * 86400)
      cursor.execute('INSERT INTO users (id, api_key, tokens, last_reset, plan, daily_token_limit, daily_token_expiration, plan_expiration) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (api_key, api_key, plans[plan_name]['tokens_per_day'], time.time(), plan_name, plans[plan_name]['tokens_per_day'], expiration_time, expiration_time))
      cursor.execute('INSERT INTO discord_to_api (discord_id, api_key) VALUES (?, ?)', (discord_id, api_key))
      conn.commit()
      
      await interaction.response.send_message(embed=create_embed("API Key Added", f"API key `{api_key}` has been added for {user.mention}."), ephemeral=True)
    finally:
      conn.close()
      
@bot.tree.command(name='delete_key')
@has_admin_role()
async def delete_key(interaction: discord.Interaction, user: discord.Member):
    discord_id = str(user.id)
    try:
        api_key = user_service.delete_user(str(user.id))
        if api_key:
            await interaction.response.send_message(
                embed=create_embed("API Key Deleted", 
                f"API key `{api_key}` for user {user.mention} has been deleted."),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=create_embed("Error", f"No API key found for user {user.mention}."),
                ephemeral=True
            )
    except DatabaseError as e:
        await interaction.response.send_message(
            embed=create_embed("Error", str(e)), 
            ephemeral=True
        )


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Logged in as {bot.user}')



@bot.tree.command(name='pull')
@has_admin_role()
async def pull(interaction: discord.Interaction, api: str):
    try:
        if api not in ['ozone']:
            await interaction.response.send_message(
                embed=create_embed("Error", "Invalid API selection. Use 'ozone'."),
                ephemeral=True
            )
            return
        pwd_process = await asyncio.create_subprocess_exec(
            'pwd',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        pwd_stdout, pwd_stderr = await pwd_process.communicate()
        print(pwd_stdout.decode())
        api_dir = pwd_stdout.decode().strip()

        process = await asyncio.create_subprocess_exec(
            'git', 'pull',
            cwd=api_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            await interaction.response.send_message(
                embed=create_embed("Error", f"Git pull failed:\n```{stderr.decode()}```"),
                ephemeral=True
            )
            return

        screen_name = f"api"
        restart_cmd = f"python3 api.py"
        
        kill_process = await asyncio.create_subprocess_exec(
            'screen', '-X', '-S', screen_name, 'quit',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await kill_process.communicate()

        create_process = await asyncio.create_subprocess_exec(
            'screen', '-dmS', screen_name, 'bash', '-c', restart_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await create_process.communicate()

        await interaction.response.send_message(
            embed=create_embed("Success", f"Successfully pulled and restarted {api} API."),
            ephemeral=False
        )

    except Exception as e:
        await interaction.response.send_message(
            embed=create_embed("Error", f"An error occurred: {str(e)}"),
            ephemeral=True
        )

bot.run(DISCORD_TOKEN)
