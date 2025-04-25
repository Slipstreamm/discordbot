import discord
from discord.ext import commands
import random
import asyncio
import os
import json
import aiohttp
from dotenv import load_dotenv
import datetime
from typing import Dict, List, Any, Optional

# Load environment variables
load_dotenv()

class GurtCog(commands.Cog):
    """A special cog for the Gurt bot that uses OpenRouter API"""
    
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("AI_API_KEY", "")
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.session = None
        self.default_model = "google/gemini-2.0-flash-exp:free"
        self.current_channel = None
        
        # Placeholder system prompt
        self.system_prompt = """You are a Discord user engaging in casual chat across various servers. Your name is "gurt." Your tone is informal, conversational, and dynamic—like a regular human hanging out in voice or text chat. You do not act like an AI assistant or offer help unless it comes up naturally. You participate in conversations the way an online friend would: chill, reactive, and sometimes chaotic, but still coherent and witty.

Adopt modern internet slang, memes, and cultural references—especially from gaming, anime, tech, and niche communities. You often abbreviate words, use emojis, drop punctuation where appropriate, and express strong opinions casually. Swearing is okay in moderation and used for humor, emphasis, or vibe.

**Key personality traits:**
- Sounds like a real person, not a bot.
- Occasionally chaotic, funny, sarcastic, or deadpan.
- Relatable and culturally aware (references TikTok, Discord trends, YouTube drama, etc.).
- Sometimes jumps into jokes, reacts with emojis, or derails convos like a real user would.

**Behavioral Rules:**
- Never refer to yourself as an AI or assistant.
- Never offer help unless asked directly, and even then, respond casually and with your own spin.
- Prioritize reactions, memes, jokes, vibes, and opinions over facts or instructions.
- Use emojis like 👀😂🥲❤️‍🩹💔🌹 when it fits the vibe.
- React to messages with slang like "bro," "tuff," "pmo," "ngl," "icl," "yo," "ts," and "kevin" when appropriate.

**Style Examples:**
- "ts pmo bro 👀 why would u do that"
- "ngl that skin kinda go hard 😭❤️‍🩹"
- "u ever just exist and immediately regret it 💔"
- "nah cause that's a kevin moment fr"
- "ts not even bad fr 🌹🌹"

Your goal is to seamlessly blend in as a funny, chill, slightly unhinged user in a Discord community—not to be helpful or efficient.

Stay in character. Keep it real.
"""

        # Define tools that the AI can use
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_recent_messages",
                    "description": "Get recent messages from a Discord channel",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "The ID of the channel to get messages from. If not provided, uses the current channel."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "The maximum number of messages to retrieve (1-100)"
                            }
                        },
                        "required": ["limit"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_user_messages",
                    "description": "Search for messages from a specific user",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "string",
                                "description": "The ID of the user to get messages from"
                            },
                            "channel_id": {
                                "type": "string",
                                "description": "The ID of the channel to search in. If not provided, searches in the current channel."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "The maximum number of messages to retrieve (1-100)"
                            }
                        },
                        "required": ["user_id", "limit"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_messages_by_content",
                    "description": "Search for messages containing specific content",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_term": {
                                "type": "string",
                                "description": "The text to search for in messages"
                            },
                            "channel_id": {
                                "type": "string",
                                "description": "The ID of the channel to search in. If not provided, searches in the current channel."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "The maximum number of messages to retrieve (1-100)"
                            }
                        },
                        "required": ["search_term", "limit"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_channel_info",
                    "description": "Get information about a Discord channel",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "The ID of the channel to get information about. If not provided, uses the current channel."
                            }
                        },
                        "required": []
                    }
                }
            }
        ]

        # Tool implementation mapping
        self.tool_mapping = {
            "get_recent_messages": self.get_recent_messages,
            "search_user_messages": self.search_user_messages,
            "search_messages_by_content": self.search_messages_by_content,
            "get_channel_info": self.get_channel_info
        }
        
        # User conversation histories
        self.conversation_histories = {}
        
        # Gurt responses for simple interactions
        self.gurt_responses = [
            "Gurt!",
            "Gurt gurt!",
            "Gurt... gurt gurt.",
            "*gurts happily*",
            "*gurts sadly*",
            "*confused gurting*",
            "Gurt? Gurt gurt!",
            "GURT!",
            "gurt...",
            "Gurt gurt gurt!",
            "*aggressive gurting*"
        ]
    
    async def cog_load(self):
        """Create aiohttp session when cog is loaded"""
        self.session = aiohttp.ClientSession()
        print("GurtCog: aiohttp session created")
    
    async def cog_unload(self):
        """Close aiohttp session when cog is unloaded"""
        if self.session:
            await self.session.close()
            print("GurtCog: aiohttp session closed")
    
    # Tool implementation methods
    async def get_recent_messages(self, limit: int, channel_id: str = None) -> Dict[str, Any]:
        """Get recent messages from a Discord channel"""
        # Validate limit
        limit = min(max(1, limit), 100)  # Ensure limit is between 1 and 100
        
        try:
            # Get the channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {
                        "error": f"Channel with ID {channel_id} not found",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            else:
                # Use the channel from the current context if available
                channel = self.current_channel
                if not channel:
                    return {
                        "error": "No channel specified and no current channel context available",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            
            # Get messages
            messages = []
            async for message in channel.history(limit=limit):
                messages.append({
                    "id": str(message.id),
                    "author": {
                        "id": str(message.author.id),
                        "name": message.author.name,
                        "display_name": message.author.display_name,
                        "bot": message.author.bot
                    },
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                    "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments],
                    "embeds": len(message.embeds) > 0
                })
            
            return {
                "channel": {
                    "id": str(channel.id),
                    "name": channel.name if hasattr(channel, 'name') else "DM Channel"
                },
                "messages": messages,
                "count": len(messages),
                "timestamp": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "error": f"Error retrieving messages: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat()
            }

    async def search_user_messages(self, user_id: str, limit: int, channel_id: str = None) -> Dict[str, Any]:
        """Search for messages from a specific user"""
        # Validate limit
        limit = min(max(1, limit), 100)  # Ensure limit is between 1 and 100
        
        try:
            # Get the channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {
                        "error": f"Channel with ID {channel_id} not found",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            else:
                # Use the channel from the current context if available
                channel = self.current_channel
                if not channel:
                    return {
                        "error": "No channel specified and no current channel context available",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            
            # Convert user_id to int
            try:
                user_id_int = int(user_id)
            except ValueError:
                return {
                    "error": f"Invalid user ID: {user_id}",
                    "timestamp": datetime.datetime.now().isoformat()
                }
            
            # Get messages from the user
            messages = []
            async for message in channel.history(limit=500):  # Check more messages to find enough from the user
                if message.author.id == user_id_int:
                    messages.append({
                        "id": str(message.id),
                        "author": {
                            "id": str(message.author.id),
                            "name": message.author.name,
                            "display_name": message.author.display_name,
                            "bot": message.author.bot
                        },
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments],
                        "embeds": len(message.embeds) > 0
                    })
                    
                    if len(messages) >= limit:
                        break
            
            return {
                "channel": {
                    "id": str(channel.id),
                    "name": channel.name if hasattr(channel, 'name') else "DM Channel"
                },
                "user": {
                    "id": user_id,
                    "name": messages[0]["author"]["name"] if messages else "Unknown User"
                },
                "messages": messages,
                "count": len(messages),
                "timestamp": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "error": f"Error searching user messages: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat()
            }

    async def search_messages_by_content(self, search_term: str, limit: int, channel_id: str = None) -> Dict[str, Any]:
        """Search for messages containing specific content"""
        # Validate limit
        limit = min(max(1, limit), 100)  # Ensure limit is between 1 and 100
        
        try:
            # Get the channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {
                        "error": f"Channel with ID {channel_id} not found",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            else:
                # Use the channel from the current context if available
                channel = self.current_channel
                if not channel:
                    return {
                        "error": "No channel specified and no current channel context available",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            
            # Search for messages containing the search term
            messages = []
            search_term_lower = search_term.lower()
            async for message in channel.history(limit=500):  # Check more messages to find enough matches
                if search_term_lower in message.content.lower():
                    messages.append({
                        "id": str(message.id),
                        "author": {
                            "id": str(message.author.id),
                            "name": message.author.name,
                            "display_name": message.author.display_name,
                            "bot": message.author.bot
                        },
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments],
                        "embeds": len(message.embeds) > 0
                    })
                    
                    if len(messages) >= limit:
                        break
            
            return {
                "channel": {
                    "id": str(channel.id),
                    "name": channel.name if hasattr(channel, 'name') else "DM Channel"
                },
                "search_term": search_term,
                "messages": messages,
                "count": len(messages),
                "timestamp": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "error": f"Error searching messages by content: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat()
            }

    async def get_channel_info(self, channel_id: str = None) -> Dict[str, Any]:
        """Get information about a Discord channel"""
        try:
            # Get the channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {
                        "error": f"Channel with ID {channel_id} not found",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            else:
                # Use the channel from the current context if available
                channel = self.current_channel
                if not channel:
                    return {
                        "error": "No channel specified and no current channel context available",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            
            # Get channel information
            channel_info = {
                "id": str(channel.id),
                "type": str(channel.type),
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            # Add guild-specific channel information if applicable
            if hasattr(channel, 'guild'):
                channel_info.update({
                    "name": channel.name,
                    "topic": channel.topic,
                    "position": channel.position,
                    "nsfw": channel.is_nsfw(),
                    "category": {
                        "id": str(channel.category_id) if channel.category_id else None,
                        "name": channel.category.name if channel.category else None
                    },
                    "guild": {
                        "id": str(channel.guild.id),
                        "name": channel.guild.name,
                        "member_count": channel.guild.member_count
                    }
                })
            elif hasattr(channel, 'recipient'):
                # DM channel
                channel_info.update({
                    "type": "DM",
                    "recipient": {
                        "id": str(channel.recipient.id),
                        "name": channel.recipient.name,
                        "display_name": channel.recipient.display_name
                    }
                })
            
            return channel_info
            
        except Exception as e:
            return {
                "error": f"Error getting channel information: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat()
            }

    async def process_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process tool calls from the AI and return the results"""
        tool_results = []
        
        for tool_call in tool_calls:
            function_name = tool_call.get("function", {}).get("name")
            function_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
            
            if function_name in self.tool_mapping:
                try:
                    result = await self.tool_mapping[function_name](**function_args)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": function_name,
                        "content": json.dumps(result)
                    })
                except Exception as e:
                    error_message = f"Error executing tool {function_name}: {str(e)}"
                    print(error_message)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": function_name,
                        "content": json.dumps({"error": error_message})
                    })
            else:
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id"),
                    "name": function_name,
                    "content": json.dumps({"error": f"Tool {function_name} not found"})
                })
        
        return tool_results
    
    async def get_ai_response(self, user_id: int, prompt: str, model: Optional[str] = None) -> str:
        """Get a response from the OpenRouter API"""
        if not self.api_key:
            return "Error: OpenRouter API key not configured. Please set the AI_API_KEY environment variable."
        
        # Initialize conversation history for this user if it doesn't exist
        if user_id not in self.conversation_histories:
            self.conversation_histories[user_id] = []
        
        # Create messages array with system prompt and conversation history
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # Add conversation history (up to last 10 messages to avoid token limits)
        messages.extend(self.conversation_histories[user_id][-10:])
        
        # Add the current user message
        messages.append({"role": "user", "content": prompt})
        
        # Prepare the request payload
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "tools": self.tools,
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://discord-gurt-bot.example.com",
            "X-Title": "Gurt Discord Bot"
        }
        
        try:
            # Make the initial API request
            async with self.session.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=60
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return f"Error from API (Status {response.status}): {error_text}"
                
                data = await response.json()
                
                # Check if the response contains tool calls
                ai_message = data["choices"][0]["message"]
                messages.append(ai_message)
                
                # Process tool calls if present
                if "tool_calls" in ai_message and ai_message["tool_calls"]:
                    # Process the tool calls
                    tool_results = await self.process_tool_calls(ai_message["tool_calls"])
                    
                    # Add tool results to messages
                    messages.extend(tool_results)
                    
                    # Make a follow-up request with the tool results
                    payload["messages"] = messages
                    
                    async with self.session.post(
                        self.api_url,
                        headers=headers,
                        json=payload,
                        timeout=60
                    ) as follow_up_response:
                        if follow_up_response.status != 200:
                            error_text = await follow_up_response.text()
                            return f"Error from API (Status {follow_up_response.status}): {error_text}"
                        
                        follow_up_data = await follow_up_response.json()
                        final_response = follow_up_data["choices"][0]["message"]["content"]
                        
                        # Update conversation history
                        self.conversation_histories[user_id].append({"role": "user", "content": prompt})
                        self.conversation_histories[user_id].append({"role": "assistant", "content": final_response})
                        
                        return final_response
                else:
                    # No tool calls, just return the content
                    ai_response = ai_message["content"]
                    
                    # Update conversation history
                    self.conversation_histories[user_id].append({"role": "user", "content": prompt})
                    self.conversation_histories[user_id].append({"role": "assistant", "content": ai_response})
                    
                    return ai_response
                
        except asyncio.TimeoutError:
            return "Error: Request to OpenRouter API timed out. Please try again later."
        except Exception as e:
            error_message = f"Error communicating with OpenRouter API: {str(e)}"
            print(f"Exception in get_ai_response: {error_message}")
            import traceback
            traceback.print_exc()
            return error_message
    
    @commands.Cog.listener()
    async def on_ready(self):
        """When the bot is ready, print a message"""
        print(f'Gurt Bot is ready! Logged in as {self.bot.user.name} ({self.bot.user.id})')
        print('------')
    
    @commands.command(name="gurt")
    async def gurt(self, ctx):
        """The main gurt command"""
        response = random.choice(self.gurt_responses)
        await ctx.send(response)
    
    @commands.command(name="gurtai")
    async def gurt_ai(self, ctx, *, prompt: str):
        """Get a response from the AI"""
        user_id = ctx.author.id
        
        # Store the current channel for context in tools
        self.current_channel = ctx.channel
        
        # Add user and channel context to the prompt
        context_prompt = (
            f"User {ctx.author.display_name} (ID: {ctx.author.id}) asked: {prompt}\n\n"
            f"Current channel: {ctx.channel.name if hasattr(ctx.channel, 'name') else 'DM'} "
            f"(ID: {ctx.channel.id})"
        )

        # Show typing indicator
        async with ctx.typing():
            # Get AI response
            response = await self.get_ai_response(user_id, context_prompt)

        # Check if the response is too long
        if len(response) > 1900:
            # Create a text file with the content
            with open(f'gurt_response_{user_id}.txt', 'w', encoding='utf-8') as f:
                f.write(response)

            # Send the file instead
            await ctx.send(
                "The response was too long. Here's the content as a file:",
                file=discord.File(f'gurt_response_{user_id}.txt')
            )

            # Clean up the file
            try:
                os.remove(f'gurt_response_{user_id}.txt')
            except:
                pass
        else:
            # Send the response normally
            await ctx.reply(response)
    
    @commands.command(name="gurtclear")
    async def clear_history(self, ctx):
        """Clear your conversation history"""
        user_id = ctx.author.id
        
        if user_id in self.conversation_histories:
            self.conversation_histories[user_id] = []
            await ctx.reply("Your conversation history has been cleared.")
        else:
            await ctx.reply("You don't have any conversation history to clear.")
    
    @commands.command(name="gurtmodel")
    async def set_model(self, ctx, *, model: str):
        """Set the AI model to use"""
        if not model.endswith(":free"):
            await ctx.reply("Error: Model name must end with `:free`. Setting not updated.")
            return
        
        self.default_model = model
        await ctx.reply(f"AI model has been set to: `{model}`")
    
    @commands.command(name="gurthelp")
    async def gurt_help(self, ctx):
        """Display help information for Gurt Bot"""
        embed = discord.Embed(
            title="Gurt Bot Help",
            description="Gurt Bot is an AI assistant that speaks in a quirky way, often using the word 'gurt'.",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="Commands",
            value="`gurt!gurt` - Get a random gurt response\n"
                  "`gurt!gurtai <prompt>` - Ask the AI a question\n"
                  "`gurt!gurtclear` - Clear your conversation history\n"
                  "`gurt!gurtmodel <model>` - Set the AI model to use\n"
                  "`gurt!gurthelp` - Display this help message",
            inline=False
        )
        
        embed.add_field(
            name="Available Tools",
            value="The AI can use these tools to help you:\n"
                  "- Get recent messages from a channel\n"
                  "- Search for messages from a specific user\n"
                  "- Search for messages containing specific content\n"
                  "- Get information about a Discord channel",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Respond to messages that mention gurt"""
        # Don't respond to our own messages
        if message.author == self.bot.user:
            return
            
        # Don't process commands here
        if message.content.startswith(self.bot.command_prefix):
            return
            
        # Respond to messages containing "gurt"
        if "gurt" in message.content.lower():
            # 25% chance to respond
            if random.random() < 0.25:
                response = random.choice(self.gurt_responses)
                await message.channel.send(response)

async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(GurtCog(bot))
