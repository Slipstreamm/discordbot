import discord
from discord.ext import commands
import traceback
import os
import datetime

# Global function for storing interaction content
store_interaction_content = None

# Utility functions to store message content before sending
async def store_and_send(ctx_or_interaction, content, **kwargs):
    """Store the message content and then send it."""
    # Store the content for potential error handling
    if isinstance(ctx_or_interaction, commands.Context):
        ctx_or_interaction._last_message_content = content
        return await ctx_or_interaction.send(content, **kwargs)
    else:  # It's an interaction
        ctx_or_interaction._last_response_content = content
        if not ctx_or_interaction.response.is_done():
            return await ctx_or_interaction.response.send_message(content, **kwargs)
        else:
            return await ctx_or_interaction.followup.send(content, **kwargs)

async def store_and_reply(ctx, content, **kwargs):
    """Store the message content and then reply to the message."""
    ctx._last_message_content = content
    return await ctx.reply(content, **kwargs)

def extract_message_content(ctx_or_interaction):
    """Extract message content from a Context or Interaction object."""
    content = None

    # Check if this is an AI command error
    is_ai_command = False
    if isinstance(ctx_or_interaction, commands.Context) and hasattr(ctx_or_interaction, 'command'):
        is_ai_command = ctx_or_interaction.command and ctx_or_interaction.command.name == 'ai'
    elif hasattr(ctx_or_interaction, 'command') and ctx_or_interaction.command:
        is_ai_command = ctx_or_interaction.command.name == 'ai'

    # For AI commands, try to load from the ai_response.txt file if it exists
    if is_ai_command and os.path.exists('ai_response.txt'):
        try:
            with open('ai_response.txt', 'r', encoding='utf-8') as f:
                content = f.read()
                if content:
                    return content
        except Exception as e:
            print(f"Error reading ai_response.txt: {e}")

    # For interactions, try to get content from the AI cog's dictionary
    if not isinstance(ctx_or_interaction, commands.Context) and is_ai_command:
        try:
            # Try to import the dictionary from the AI cog
            from cogs.ai_cog import interaction_responses

            # Get the interaction ID
            interaction_id = getattr(ctx_or_interaction, 'id', None)
            if interaction_id and interaction_id in interaction_responses:
                content = interaction_responses[interaction_id]
                print(f"Retrieved content for interaction {interaction_id} from dictionary")
                if content:
                    return content
        except Exception as e:
            print(f"Error retrieving from interaction_responses dictionary: {e}")

    if isinstance(ctx_or_interaction, commands.Context):
        # For Context objects
        if hasattr(ctx_or_interaction, '_last_message_content'):
            content = ctx_or_interaction._last_message_content
        elif hasattr(ctx_or_interaction, 'message') and hasattr(ctx_or_interaction.message, 'content'):
            content = ctx_or_interaction.message.content
        elif hasattr(ctx_or_interaction, '_internal_response'):
            content = str(ctx_or_interaction._internal_response)
        # Try to extract from command invocation
        elif hasattr(ctx_or_interaction, 'command') and hasattr(ctx_or_interaction, 'kwargs'):
            # Reconstruct command invocation
            cmd_name = ctx_or_interaction.command.name if hasattr(ctx_or_interaction.command, 'name') else 'unknown_command'
            args_str = ' '.join([str(arg) for arg in ctx_or_interaction.args[1:]]) if hasattr(ctx_or_interaction, 'args') else ''
            kwargs_str = ' '.join([f'{k}={v}' for k, v in ctx_or_interaction.kwargs.items()]) if ctx_or_interaction.kwargs else ''
            content = f"Command: {cmd_name} {args_str} {kwargs_str}".strip()
    else:
        # For Interaction objects
        if hasattr(ctx_or_interaction, '_last_response_content'):
            content = ctx_or_interaction._last_response_content
        elif hasattr(ctx_or_interaction, '_internal_response'):
            content = str(ctx_or_interaction._internal_response)
        # Try to extract from interaction data
        elif hasattr(ctx_or_interaction, 'data'):
            try:
                # Extract command name and options
                cmd_name = ctx_or_interaction.data.get('name', 'unknown_command')
                options = ctx_or_interaction.data.get('options', [])
                options_str = ' '.join([f"{opt.get('name')}={opt.get('value')}" for opt in options]) if options else ''
                content = f"Slash Command: /{cmd_name} {options_str}".strip()
            except (AttributeError, KeyError):
                # If we can't extract structured data, try to get the raw data
                content = f"Interaction Data: {str(ctx_or_interaction.data)}"

    # For AI commands, add a note if we couldn't retrieve the full response
    if is_ai_command and (not content or len(content) < 100):
        content = "The AI response was too long and could not be retrieved. " + \
                 "This is likely due to a message that exceeded Discord's length limits. " + \
                 "Please try again with a shorter prompt or request fewer details."

    return content

def log_error_details(ctx_or_interaction, error, content=None):
    """Log detailed error information to a file for debugging."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_dir = "error_logs"

    # Create logs directory if it doesn't exist
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create a unique filename based on timestamp
    log_file = os.path.join(log_dir, f"error_{timestamp.replace(':', '-').replace(' ', '_')}.log")

    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"=== Error Log: {timestamp} ===\n\n")

        # Log error details
        f.write(f"Error Type: {type(error).__name__}\n")
        f.write(f"Error Message: {str(error)}\n\n")

        # Log error attributes
        if hasattr(error, '__dict__'):
            f.write("Error Attributes:\n")
            for key, value in error.__dict__.items():
                f.write(f"  {key}: {value}\n")
            f.write("\n")

        # Log cause if available
        if error.__cause__:
            f.write(f"Cause: {type(error.__cause__).__name__}\n")
            f.write(f"Cause Message: {str(error.__cause__)}\n\n")

            if hasattr(error.__cause__, '__dict__'):
                f.write("Cause Attributes:\n")
                for key, value in error.__cause__.__dict__.items():
                    f.write(f"  {key}: {value}\n")
                f.write("\n")

        # Log traceback
        f.write("Traceback:\n")
        f.write(traceback.format_exc())
        f.write("\n")

        # Log context/interaction details
        f.write("Context/Interaction Details:\n")
        if isinstance(ctx_or_interaction, commands.Context):
            f.write(f"  Type: Context\n")
            if hasattr(ctx_or_interaction, 'command') and ctx_or_interaction.command:
                f.write(f"  Command: {ctx_or_interaction.command.name}\n")
            if hasattr(ctx_or_interaction, 'author') and ctx_or_interaction.author:
                f.write(f"  Author: {ctx_or_interaction.author.name} (ID: {ctx_or_interaction.author.id})\n")
            if hasattr(ctx_or_interaction, 'guild') and ctx_or_interaction.guild:
                f.write(f"  Guild: {ctx_or_interaction.guild.name} (ID: {ctx_or_interaction.guild.id})\n")
            if hasattr(ctx_or_interaction, 'channel') and ctx_or_interaction.channel:
                f.write(f"  Channel: {ctx_or_interaction.channel.name} (ID: {ctx_or_interaction.channel.id})\n")
        else:
            f.write(f"  Type: Interaction\n")
            if hasattr(ctx_or_interaction, 'user') and ctx_or_interaction.user:
                f.write(f"  User: {ctx_or_interaction.user.name} (ID: {ctx_or_interaction.user.id})\n")
            if hasattr(ctx_or_interaction, 'guild') and ctx_or_interaction.guild:
                f.write(f"  Guild: {ctx_or_interaction.guild.name} (ID: {ctx_or_interaction.guild.id})\n")
            if hasattr(ctx_or_interaction, 'channel') and ctx_or_interaction.channel:
                f.write(f"  Channel: {ctx_or_interaction.channel.name} (ID: {ctx_or_interaction.channel.id})\n")
            if hasattr(ctx_or_interaction, 'command') and ctx_or_interaction.command:
                f.write(f"  Command: {ctx_or_interaction.command.name}\n")
        f.write("\n")

        # Log message content if available
        if content:
            f.write("Message Content:\n")
            f.write(content)
            f.write("\n")

    print(f"Error details logged to {log_file}")
    return log_file

def patch_discord_methods():
    """Patch Discord methods to store message content before sending."""
    # Save original methods for Context
    original_context_send = commands.Context.send
    original_context_reply = commands.Context.reply

    # Patch Context.send
    async def patched_context_send(self, content=None, **kwargs):
        if content is not None:
            self._last_message_content = content
        return await original_context_send(self, content, **kwargs)

    # Patch Context.reply
    async def patched_context_reply(self, content=None, **kwargs):
        if content is not None:
            self._last_message_content = content
        return await original_context_reply(self, content, **kwargs)

    # Apply Context patches
    commands.Context.send = patched_context_send
    commands.Context.reply = patched_context_reply

    # For Interaction, we'll use a simpler approach that doesn't rely on patching
    # the internal classes, which can vary between Discord.py versions

    # Instead, we'll add a utility function to store content that can be called
    # before sending messages with interactions

    # This function will be available globally for use in commands
    global store_interaction_content
    def store_interaction_content(interaction, content):
        """Store content in an interaction for potential error recovery"""
        if interaction and content:
            try:
                # Try to import the dictionary from the AI cog
                try:
                    from cogs.ai_cog import interaction_responses

                    # Store using the interaction ID as the key
                    interaction_id = getattr(interaction, 'id', None)
                    if interaction_id:
                        interaction_responses[interaction_id] = content
                        print(f"Stored response for interaction {interaction_id} in dictionary from error_handler")
                        return True
                except ImportError:
                    pass

                # Fallback: try to set attribute directly (may fail)
                interaction._last_response_content = content
                return True
            except Exception as e:
                print(f"Warning: Failed to store interaction content in error_handler: {e}")
        return False

    print("Discord Context methods patched successfully")

async def send_error_embed_to_owner(ctx_or_interaction, error):
    """Send an embed with error details to the bot owner."""
    user_id = 452666956353503252  # Owner user ID
    
    try:
        # Get the bot instance
        bot_instance = None
        if isinstance(ctx_or_interaction, commands.Context):
            bot_instance = ctx_or_interaction.bot
        elif hasattr(ctx_or_interaction, 'bot'):
            bot_instance = ctx_or_interaction.bot
        elif hasattr(ctx_or_interaction, 'client'):
            bot_instance = ctx_or_interaction.client
            
        # Try to get from global accessor if not found
        if not bot_instance:
            try:
                from global_bot_accessor import get_bot_instance
                bot_instance = get_bot_instance()
            except ImportError:
                print("Failed to import global_bot_accessor")
            except Exception as e:
                print(f"Error getting bot instance from global_bot_accessor: {e}")
        
        if not bot_instance:
            print("Failed to get bot instance for sending error embed to owner")
            return
            
        # Get owner user
        owner = await bot_instance.fetch_user(user_id)
        if not owner:
            print(f"Failed to fetch owner user with ID {user_id}")
            return
            
        # Create the embed
        embed = discord.Embed(
            title="❌ Error Report",
            description=f"**Error Type:** {type(error).__name__}\n**Message:** {str(error)}",
            color=0xFF0000,  # Red color
            timestamp=datetime.datetime.now()
        )
        
        # Add command info
        command_name = "Unknown"
        if isinstance(ctx_or_interaction, commands.Context):
            if hasattr(ctx_or_interaction, 'command') and ctx_or_interaction.command:
                command_name = ctx_or_interaction.command.name
            embed.add_field(
                name="Command",
                value=f"`{command_name}`",
                inline=True
            )
        else:  # It's an interaction
            if hasattr(ctx_or_interaction, 'command') and ctx_or_interaction.command:
                command_name = ctx_or_interaction.command.name
            embed.add_field(
                name="Slash Command",
                value=f"`/{command_name}`",
                inline=True
            )
        
        # Add user info
        user_info = "Unknown"
        if isinstance(ctx_or_interaction, commands.Context):
            if ctx_or_interaction.author:
                user_info = f"{ctx_or_interaction.author.name} (ID: {ctx_or_interaction.author.id})"
        else:  # It's an interaction
            if ctx_or_interaction.user:
                user_info = f"{ctx_or_interaction.user.name} (ID: {ctx_or_interaction.user.id})"
        
        embed.add_field(
            name="User",
            value=user_info,
            inline=True
        )
        
        # Add guild and channel info
        guild_info = "DM"
        channel_info = "DM"
        
        if isinstance(ctx_or_interaction, commands.Context):
            if ctx_or_interaction.guild:
                guild_info = f"{ctx_or_interaction.guild.name} (ID: {ctx_or_interaction.guild.id})"
            if ctx_or_interaction.channel:
                channel_info = f"#{ctx_or_interaction.channel.name} (ID: {ctx_or_interaction.channel.id})"
        else:  # It's an interaction
            if ctx_or_interaction.guild:
                guild_info = f"{ctx_or_interaction.guild.name} (ID: {ctx_or_interaction.guild.id})"
            if ctx_or_interaction.channel:
                channel_info = f"#{ctx_or_interaction.channel.name} (ID: {ctx_or_interaction.channel.id})"
        
        embed.add_field(
            name="Server",
            value=guild_info,
            inline=True
        )
        
        embed.add_field(
            name="Channel",
            value=channel_info,
            inline=True
        )
        
        # Add timestamp field
        embed.add_field(
            name="Timestamp",
            value=f"<t:{int(datetime.datetime.now().timestamp())}:F>",
            inline=True
        )
        
        # Add traceback as a field (truncated)
        tb_str = traceback.format_exc()
        if len(tb_str) > 1000:
            tb_str = tb_str[:997] + "..."
        
        embed.add_field(
            name="Traceback",
            value=f"```python\n{tb_str}\n```",
            inline=False
        )
        
        # Add cause if available
        if error.__cause__:
            embed.add_field(
                name="Cause",
                value=f"```{type(error.__cause__).__name__}: {str(error.__cause__)}\n```",
                inline=False
            )
        
        # Extract content for context
        try:
            content = extract_message_content(ctx_or_interaction)
            if content and len(content) > 1000:
                content = content[:997] + "..."
            if content:
                embed.add_field(
                    name="Message Content",
                    value=f"```\n{content}\n```",
                    inline=False
                )
        except Exception as e:
            embed.add_field(
                name="Content Extraction Error",
                value=f"Failed to extract message content: {str(e)}",
                inline=False
            )
        
        # Set footer
        embed.set_footer(text=f"Error ID: {datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
        
        # Send the embed to the owner
        await owner.send(embed=embed)
        
    except Exception as e:
        print(f"Error sending error embed to owner: {e}")
        # Fall back to simple text message if embed fails
        try:
            if bot_instance and (owner := await bot_instance.fetch_user(user_id)):
                await owner.send(f"Error occurred but failed to create embed: {str(error)}\nEmbed error: {str(e)}")
        except:
            print("Complete failure in error reporting system")

async def handle_error(ctx_or_interaction, error):
    user_id = 452666956353503252  # Owner user ID
    
    # Handle missing required argument errors

    if isinstance(error, commands.NotOwner):
        message = "You are not the owner of this bot."
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(message)
        else:
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(message, ephemeral=True)
            else:
                await ctx_or_interaction.followup.send(message, ephemeral=True)
                
        # Also send to owner in an embed

    if isinstance(error, commands.MissingRequiredArgument):
        missing_arg = error.param.name if hasattr(error, 'param') else 'an argument'
        message = f"Missing required argument: `{missing_arg}`. Please provide all required arguments."
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(message)
        else:
            if not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.send_message(message, ephemeral=True)
            else:
                await ctx_or_interaction.followup.send(message, ephemeral=True)
                
        # Also send to owner in an embed
        await send_error_embed_to_owner(ctx_or_interaction, error)
        return

    # Special handling for interaction timeout errors (10062: Unknown interaction)
    if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.NotFound) and error.original.code == 10062:
        print(f"Interaction timeout error (10062): {error}")
        # This error occurs when Discord's interaction token expires (after 3 seconds)
        # We can't respond to the interaction anymore, so we'll just log it and notify the owner
        await send_error_embed_to_owner(ctx_or_interaction, error)
        return

    error_message = f"An error occurred: {error}"

    # Check if this is an AI command error
    is_ai_command = False
    if isinstance(ctx_or_interaction, commands.Context) and hasattr(ctx_or_interaction, 'command'):
        is_ai_command = ctx_or_interaction.command and ctx_or_interaction.command.name == 'ai'
    elif hasattr(ctx_or_interaction, 'command') and ctx_or_interaction.command:
        is_ai_command = ctx_or_interaction.command.name == 'ai'

    # For AI command errors with HTTPException, try to handle specially
    if is_ai_command and isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException):
        if error.original.code == 50035 and "Must be 4000 or fewer in length" in str(error.original):
            # Try to get the AI response from the stored content
            if isinstance(ctx_or_interaction, commands.Context) and hasattr(ctx_or_interaction, '_last_message_content'):
                content = ctx_or_interaction._last_message_content
                # Save to file and send
                with open('ai_response.txt', 'w', encoding='utf-8') as f:
                    f.write(content)
                await ctx_or_interaction.send("The AI response was too long. Here's the content as a file:", file=discord.File('ai_response.txt'))
                # Also notify the owner
                await send_error_embed_to_owner(ctx_or_interaction, error)
                return
            elif hasattr(ctx_or_interaction, '_last_response_content'):
                content = ctx_or_interaction._last_response_content
                # Save to file and send
                with open('ai_response.txt', 'w', encoding='utf-8') as f:
                    f.write(content)
                if not ctx_or_interaction.response.is_done():
                    await ctx_or_interaction.response.send_message("The AI response was too long. Here's the content as a file:", file=discord.File('ai_response.txt'))
                else:
                    await ctx_or_interaction.followup.send("The AI response was too long. Here's the content as a file:", file=discord.File('ai_response.txt'))
                # Also notify the owner
                await send_error_embed_to_owner(ctx_or_interaction, error)
                return

    # Extract message content for logging
    content = extract_message_content(ctx_or_interaction)

    # Log error details to file
    log_file = log_error_details(ctx_or_interaction, error, content)

    # Check if the command runner is the owner
    is_owner = False
    if isinstance(ctx_or_interaction, commands.Context):
        is_owner = ctx_or_interaction.author.id == user_id
    else:
        is_owner = ctx_or_interaction.user.id == user_id

    # Only send detailed error DM if the command runner is the owner
    if is_owner:
        try:
            # Get the bot instance - handle both Context and Interaction objects
            bot_instance = None
            if isinstance(ctx_or_interaction, commands.Context):
                bot_instance = ctx_or_interaction.bot
            elif hasattr(ctx_or_interaction, 'bot'):
                bot_instance = ctx_or_interaction.bot
            elif hasattr(ctx_or_interaction, 'client'):
                bot_instance = ctx_or_interaction.client

            # If we couldn't get the bot instance, try to get it from the global accessor
            if not bot_instance:
                try:
                    # Import here to avoid circular imports
                    from global_bot_accessor import get_bot_instance
                    bot_instance = get_bot_instance()
                except ImportError:
                    print("Failed to import global_bot_accessor")
                except Exception as e:
                    print(f"Error getting bot instance from global_bot_accessor: {e}")

            # If we still don't have a bot instance, we can't send a DM
            if not bot_instance:
                print(f"Failed to send error DM to owner: No bot instance available")
                return

            # Now fetch the owner user
            owner = await bot_instance.fetch_user(user_id)
            if owner:
                full_error = f"Full error details:\n```\n{str(error)}\n"
                if hasattr(error, '__dict__'):
                    full_error += f"\nError attributes:\n{error.__dict__}\n"
                if error.__cause__:
                    full_error += f"\nCause:\n{str(error.__cause__)}\n"
                    if hasattr(error.__cause__, '__dict__'):
                        full_error += f"\nCause attributes:\n{error.__cause__.__dict__}\n"
                full_error += "```"

                # Add log file path to the error message
                full_error += f"\nDetailed error log saved to: `{log_file}`"

                # Try to send the log file as an attachment
                try:
                    await owner.send("Here's the detailed error log:", file=discord.File(log_file))
                    # Send a shorter message since we sent the file
                    short_error = f"Error: {str(error)}"
                    if error.__cause__:
                        short_error += f"\nCause: {str(error.__cause__)}"
                    await owner.send(short_error)
                except discord.HTTPException:
                    # If sending the file fails, fall back to text messages
                    # Split long messages if needed
                    if len(full_error) > 1900:
                        parts = [full_error[i:i+1900] for i in range(0, len(full_error), 1900)]
                        for i, part in enumerate(parts):
                            await owner.send(f"Part {i+1}/{len(parts)}:\n{part}")
                    else:
                        await owner.send(full_error)
        except Exception as e:
            print(f"Failed to send error DM to owner: {e}")

    # Determine the file name to use for saving content
    file_name = 'message.txt'

    # Special handling for AI command errors
    if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException):
        # Check if this is an AI command
        is_ai_command = False
        if isinstance(ctx_or_interaction, commands.Context) and hasattr(ctx_or_interaction, 'command'):
            is_ai_command = ctx_or_interaction.command and ctx_or_interaction.command.name == 'ai'
        elif hasattr(ctx_or_interaction, 'command') and ctx_or_interaction.command:
            is_ai_command = ctx_or_interaction.command.name == 'ai'

        # If it's an AI command, use a different file name
        if is_ai_command:
            file_name = 'ai_response.txt'

    # Handle message too long error (HTTP 400 - Code 50035 or 40005 for file uploads)
    if (isinstance(error, discord.HTTPException) and
        ((error.code == 50035 and ("Must be 4000 or fewer in length" in str(error) or "Must be 2000 or fewer in length" in str(error))) or
         (error.code == 40005 and "Request entity too large" in str(error)))) or \
       (isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException) and
        ((error.original.code == 50035 and ("Must be 4000 or fewer in length" in str(error.original) or "Must be 2000 or fewer in length" in str(error.original))) or
         (error.original.code == 40005 and "Request entity too large" in str(error.original)))):
        # Try to extract the actual content from the error
        content = None

        # Handle CommandInvokeError specially
        if isinstance(error, commands.CommandInvokeError):
            # Use the original error for extraction
            original_error = error.original
            if isinstance(original_error, discord.HTTPException):
                content = original_error.text if hasattr(original_error, 'text') else None
        # If it's a wrapped error, get the original error's content
        elif isinstance(error.__cause__, discord.HTTPException):
            content = error.__cause__.text if hasattr(error.__cause__, 'text') else None
        else:
            content = error.text if hasattr(error, 'text') else None

        # If content is not available in the error, try to retrieve it from the context/interaction
        if not content or len(content) < 10:  # If content is missing or too short to be the actual message
            # Try to get the original content using our utility function
            content = extract_message_content(ctx_or_interaction)

            # If we still don't have content, use a generic message
            if not content:
                content = "The original message content could not be retrieved. This is likely due to a message that exceeded Discord's length limits."

        # Try to send as a file first
        try:
            # Create a text file with the content
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(content)

            # Send the file instead
            message = f"The message was too long. Here's the content as a file:\nError details logged to: {log_file}"

            if isinstance(ctx_or_interaction, commands.Context):
                await ctx_or_interaction.send(
                    message,
                    file=discord.File(file_name)
                )
            else:
                if not ctx_or_interaction.response.is_done():
                    await ctx_or_interaction.response.send_message(
                        message,
                        file=discord.File(file_name)
                    )
                else:
                    await ctx_or_interaction.followup.send(
                        message,
                        file=discord.File(file_name)
                    )
        except discord.HTTPException as e:
            # If sending as a file also fails (e.g., file too large), split into multiple messages
            if e.code == 40005 or "Request entity too large" in str(e):
                # Split the content into chunks of 1900 characters (Discord limit is 2000)
                chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]

                # Send a notification about splitting the message
                intro_message = f"The message was too long to send as a file. Splitting into {len(chunks)} parts.\nError details logged to: {log_file}"

                if isinstance(ctx_or_interaction, commands.Context):
                    await ctx_or_interaction.send(intro_message)
                    for i, chunk in enumerate(chunks):
                        await ctx_or_interaction.send(f"Part {i+1}/{len(chunks)}:\n```\n{chunk}\n```")
                else:
                    if not ctx_or_interaction.response.is_done():
                        await ctx_or_interaction.response.send_message(intro_message)
                        for i, chunk in enumerate(chunks):
                            await ctx_or_interaction.followup.send(f"Part {i+1}/{len(chunks)}:\n```\n{chunk}\n```")
                    else:
                        await ctx_or_interaction.followup.send(intro_message)
                        for i, chunk in enumerate(chunks):
                            await ctx_or_interaction.followup.send(f"Part {i+1}/{len(chunks)}:\n```\n{chunk}\n```")
            else:
                # If it's a different error, re-raise it
                raise
        return

    # Send embed to owner for all errors that reach this point
    await send_error_embed_to_owner(ctx_or_interaction, error)
    
    # Original error handling logic
    if isinstance(ctx_or_interaction, commands.Context):
        if ctx_or_interaction.author.id == user_id:
            try:
                await ctx_or_interaction.send(content=error_message)
            except discord.Forbidden:
                await ctx_or_interaction.send("Unable to send you a DM with the error details.")
        else:
            await ctx_or_interaction.send("An error occurred while processing your command.")
    else:
        if not ctx_or_interaction.response.is_done():
            if ctx_or_interaction.user.id == user_id:
                await ctx_or_interaction.response.send_message(content=error_message, ephemeral=True)
            else:
                await ctx_or_interaction.response.send_message("An error occurred while processing your command.", ephemeral=True)
        else:
            if ctx_or_interaction.user.id == user_id:
                await ctx_or_interaction.followup.send(content=error_message, ephemeral=True)
            else:
                await ctx_or_interaction.followup.send("An error occurred while processing your command.", ephemeral=True)