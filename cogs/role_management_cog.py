import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List

# Set up logging
logger = logging.getLogger(__name__)

class RoleManagementCog(commands.Cog):
    """Cog for comprehensive role management"""

    def __init__(self, bot):
        self.bot = bot
        
        # Create the main command group for this cog
        self.role_group = app_commands.Group(
            name="role",
            description="Manage server roles"
        )
        
        # Register commands
        self.register_commands()
        
        # Add command group to the bot's tree
        self.bot.tree.add_command(self.role_group)
        
    def register_commands(self):
        """Register all commands for this cog"""
        
        # --- Create Role Command ---
        create_command = app_commands.Command(
            name="create",
            description="Create a new role",
            callback=self.role_create_callback,
            parent=self.role_group
        )
        app_commands.describe(
            name="The name of the new role",
            color="The color of the role in hex format (e.g., #FF0000 for red)",
            mentionable="Whether the role can be mentioned by everyone",
            hoist="Whether the role should be displayed separately in the member list",
            reason="The reason for creating this role"
        )(create_command)
        self.role_group.add_command(create_command)
        
        # --- Edit Role Command ---
        edit_command = app_commands.Command(
            name="edit",
            description="Edit an existing role",
            callback=self.role_edit_callback,
            parent=self.role_group
        )
        app_commands.describe(
            role="The role to edit",
            name="New name for the role",
            color="New color for the role in hex format (e.g., #FF0000 for red)",
            mentionable="Whether the role can be mentioned by everyone",
            hoist="Whether the role should be displayed separately in the member list",
            reason="The reason for editing this role"
        )(edit_command)
        self.role_group.add_command(edit_command)
        
        # --- Delete Role Command ---
        delete_command = app_commands.Command(
            name="delete",
            description="Delete a role",
            callback=self.role_delete_callback,
            parent=self.role_group
        )
        app_commands.describe(
            role="The role to delete",
            reason="The reason for deleting this role"
        )(delete_command)
        self.role_group.add_command(delete_command)
        
        # --- Add Role Command ---
        add_command = app_commands.Command(
            name="add",
            description="Add a role to a user",
            callback=self.role_add_callback,
            parent=self.role_group
        )
        app_commands.describe(
            member="The member to add the role to",
            role="The role to add",
            reason="The reason for adding this role"
        )(add_command)
        self.role_group.add_command(add_command)
        
        # --- Remove Role Command ---
        remove_command = app_commands.Command(
            name="remove",
            description="Remove a role from a user",
            callback=self.role_remove_callback,
            parent=self.role_group
        )
        app_commands.describe(
            member="The member to remove the role from",
            role="The role to remove",
            reason="The reason for removing this role"
        )(remove_command)
        self.role_group.add_command(remove_command)
        
        # --- List Roles Command ---
        list_command = app_commands.Command(
            name="list",
            description="List all roles in the server",
            callback=self.role_list_callback,
            parent=self.role_group
        )
        self.role_group.add_command(list_command)
        
        # --- Role Info Command ---
        info_command = app_commands.Command(
            name="info",
            description="View detailed information about a role",
            callback=self.role_info_callback,
            parent=self.role_group
        )
        app_commands.describe(
            role="The role to view information about"
        )(info_command)
        self.role_group.add_command(info_command)
        
        # --- Change Role Position Command ---
        position_command = app_commands.Command(
            name="position",
            description="Change a role's position in the hierarchy",
            callback=self.role_position_callback,
            parent=self.role_group
        )
        app_commands.describe(
            role="The role to move",
            position="The new position for the role (1 is the lowest, excluding @everyone)",
            reason="The reason for changing this role's position"
        )(position_command)
        self.role_group.add_command(position_command)
    
    # --- Command Callbacks ---
    
    async def role_create_callback(self, interaction: discord.Interaction, name: str, 
                                  color: Optional[str] = None, mentionable: Optional[bool] = False, 
                                  hoist: Optional[bool] = False, reason: Optional[str] = None):
        """Callback for /role create command"""
        # Check permissions
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
            return
            
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("I don't have permission to manage roles.", ephemeral=True)
            return
        
        # Parse color if provided
        role_color = discord.Color.default()
        if color:
            try:
                # Remove # if present
                if color.startswith('#'):
                    color = color[1:]
                # Convert hex to int
                role_color = discord.Color(int(color, 16))
            except ValueError:
                await interaction.response.send_message(f"Invalid color format. Please use hex format (e.g., #FF0000 for red).", ephemeral=True)
                return
        
        try:
            # Create the role
            new_role = await interaction.guild.create_role(
                name=name,
                color=role_color,
                hoist=hoist,
                mentionable=mentionable,
                reason=f"{reason or 'No reason provided'} (Created by {interaction.user})"
            )
            
            # Create an embed with role information
            embed = discord.Embed(
                title="✅ Role Created",
                description=f"Successfully created role {new_role.mention}",
                color=role_color
            )
            embed.add_field(name="Name", value=name, inline=True)
            embed.add_field(name="Color", value=str(role_color), inline=True)
            embed.add_field(name="Hoisted", value="Yes" if hoist else "No", inline=True)
            embed.add_field(name="Mentionable", value="Yes" if mentionable else "No", inline=True)
            embed.add_field(name="Created by", value=interaction.user.mention, inline=True)
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Role '{name}' created by {interaction.user} in {interaction.guild.name}")
            
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to create roles.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to create role: {e}", ephemeral=True)
    
    async def role_edit_callback(self, interaction: discord.Interaction, role: discord.Role,
                                name: Optional[str] = None, color: Optional[str] = None,
                                mentionable: Optional[bool] = None, hoist: Optional[bool] = None,
                                reason: Optional[str] = None):
        """Callback for /role edit command"""
        # Check permissions
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
            return
            
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("I don't have permission to manage roles.", ephemeral=True)
            return
            
        # Check if the role is manageable
        if not role.is_assignable() or role.is_default():
            await interaction.response.send_message("I cannot edit this role. It might be the @everyone role or higher than my highest role.", ephemeral=True)
            return
        
        # Parse color if provided
        role_color = None
        if color:
            try:
                # Remove # if present
                if color.startswith('#'):
                    color = color[1:]
                # Convert hex to int
                role_color = discord.Color(int(color, 16))
            except ValueError:
                await interaction.response.send_message(f"Invalid color format. Please use hex format (e.g., #FF0000 for red).", ephemeral=True)
                return
        
        # Store original values for the embed
        original_name = role.name
        original_color = role.color
        original_mentionable = role.mentionable
        original_hoist = role.hoist
        
        try:
            # Edit the role
            await role.edit(
                name=name if name is not None else role.name,
                color=role_color if role_color is not None else role.color,
                hoist=hoist if hoist is not None else role.hoist,
                mentionable=mentionable if mentionable is not None else role.mentionable,
                reason=f"{reason or 'No reason provided'} (Edited by {interaction.user})"
            )
            
            # Create an embed with role information
            embed = discord.Embed(
                title="✅ Role Edited",
                description=f"Successfully edited role {role.mention}",
                color=role.color
            )
            
            # Only show fields that were changed
            if name is not None and name != original_name:
                embed.add_field(name="Name", value=f"{original_name} → {name}", inline=True)
            if role_color is not None and role_color != original_color:
                embed.add_field(name="Color", value=f"{original_color} → {role.color}", inline=True)
            if hoist is not None and hoist != original_hoist:
                embed.add_field(name="Hoisted", value=f"{'Yes' if original_hoist else 'No'} → {'Yes' if hoist else 'No'}", inline=True)
            if mentionable is not None and mentionable != original_mentionable:
                embed.add_field(name="Mentionable", value=f"{'Yes' if original_mentionable else 'No'} → {'Yes' if mentionable else 'No'}", inline=True)
            
            embed.add_field(name="Edited by", value=interaction.user.mention, inline=True)
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Role '{role.name}' edited by {interaction.user} in {interaction.guild.name}")
            
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to edit this role.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to edit role: {e}", ephemeral=True)
    
    async def role_delete_callback(self, interaction: discord.Interaction, role: discord.Role, 
                                  reason: Optional[str] = None):
        """Callback for /role delete command"""
        # Check permissions
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
            return
            
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("I don't have permission to manage roles.", ephemeral=True)
            return
            
        # Check if the role is manageable
        if not role.is_assignable() or role.is_default():
            await interaction.response.send_message("I cannot delete this role. It might be the @everyone role or higher than my highest role.", ephemeral=True)
            return
        
        # Store role info for the confirmation message
        role_name = role.name
        role_color = role.color
        role_members_count = len(role.members)
        
        # Confirmation message
        embed = discord.Embed(
            title="⚠️ Confirm Role Deletion",
            description=f"Are you sure you want to delete the role **{role_name}**?",
            color=role_color
        )
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Members with this role", value=str(role_members_count), inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        
        # Create confirmation buttons
        class ConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.value = None
            
            @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
            async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != interaction.user.id:
                    await button_interaction.response.send_message("You cannot use this button.", ephemeral=True)
                    return
                
                self.value = True
                self.stop()
                
                try:
                    # Delete the role
                    await role.delete(reason=f"{reason or 'No reason provided'} (Deleted by {interaction.user})")
                    
                    # Create a success embed
                    success_embed = discord.Embed(
                        title="✅ Role Deleted",
                        description=f"Successfully deleted role **{role_name}**",
                        color=discord.Color.green()
                    )
                    success_embed.add_field(name="Deleted by", value=interaction.user.mention, inline=True)
                    if reason:
                        success_embed.add_field(name="Reason", value=reason, inline=False)
                    
                    await button_interaction.response.edit_message(embed=success_embed, view=None)
                    logger.info(f"Role '{role_name}' deleted by {interaction.user} in {interaction.guild.name}")
                    
                except discord.Forbidden:
                    await button_interaction.response.edit_message(
                        embed=discord.Embed(
                            title="❌ Error",
                            description="I don't have permission to delete this role.",
                            color=discord.Color.red()
                        ),
                        view=None
                    )
                except discord.HTTPException as e:
                    await button_interaction.response.edit_message(
                        embed=discord.Embed(
                            title="❌ Error",
                            description=f"Failed to delete role: {e}",
                            color=discord.Color.red()
                        ),
                        view=None
                    )
            
            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != interaction.user.id:
                    await button_interaction.response.send_message("You cannot use this button.", ephemeral=True)
                    return
                
                self.value = False
                self.stop()
                
                # Create a cancellation embed
                cancel_embed = discord.Embed(
                    title="❌ Cancelled",
                    description="Role deletion cancelled.",
                    color=discord.Color.red()
                )
                
                await button_interaction.response.edit_message(embed=cancel_embed, view=None)
        
        # Send the confirmation message
        view = ConfirmView()
        await interaction.response.send_message(embed=embed, view=view)
    
    async def role_add_callback(self, interaction: discord.Interaction, member: discord.Member, 
                               role: discord.Role, reason: Optional[str] = None):
        """Callback for /role add command"""
        # Check permissions
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
            return
            
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("I don't have permission to manage roles.", ephemeral=True)
            return
            
        # Check if the role is assignable
        if not role.is_assignable() or role.is_default():
            await interaction.response.send_message("I cannot assign this role. It might be the @everyone role or higher than my highest role.", ephemeral=True)
            return
            
        # Check if the member already has the role
        if role in member.roles:
            await interaction.response.send_message(f"{member.mention} already has the role {role.mention}.", ephemeral=True)
            return
        
        try:
            # Add the role to the member
            await member.add_roles(role, reason=f"{reason or 'No reason provided'} (Added by {interaction.user})")
            
            # Create an embed with role information
            embed = discord.Embed(
                title="✅ Role Added",
                description=f"Successfully added role {role.mention} to {member.mention}",
                color=role.color
            )
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Role", value=role.mention, inline=True)
            embed.add_field(name="Added by", value=interaction.user.mention, inline=True)
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Role '{role.name}' added to {member} by {interaction.user} in {interaction.guild.name}")
            
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to add roles to this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to add role: {e}", ephemeral=True)
    
    async def role_remove_callback(self, interaction: discord.Interaction, member: discord.Member, 
                                  role: discord.Role, reason: Optional[str] = None):
        """Callback for /role remove command"""
        # Check permissions
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
            return
            
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("I don't have permission to manage roles.", ephemeral=True)
            return
            
        # Check if the role is assignable
        if not role.is_assignable() or role.is_default():
            await interaction.response.send_message("I cannot remove this role. It might be the @everyone role or higher than my highest role.", ephemeral=True)
            return
            
        # Check if the member has the role
        if role not in member.roles:
            await interaction.response.send_message(f"{member.mention} doesn't have the role {role.mention}.", ephemeral=True)
            return
        
        try:
            # Remove the role from the member
            await member.remove_roles(role, reason=f"{reason or 'No reason provided'} (Removed by {interaction.user})")
            
            # Create an embed with role information
            embed = discord.Embed(
                title="✅ Role Removed",
                description=f"Successfully removed role {role.mention} from {member.mention}",
                color=role.color
            )
            embed.add_field(name="Member", value=member.mention, inline=True)
            embed.add_field(name="Role", value=role.mention, inline=True)
            embed.add_field(name="Removed by", value=interaction.user.mention, inline=True)
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Role '{role.name}' removed from {member} by {interaction.user} in {interaction.guild.name}")
            
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to remove roles from this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to remove role: {e}", ephemeral=True)
    
    async def role_list_callback(self, interaction: discord.Interaction):
        """Callback for /role list command"""
        # Check if in a guild
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        
        # Get all roles in the guild, sorted by position (highest first)
        roles = sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True)
        
        # Create an embed with role information
        embed = discord.Embed(
            title=f"Roles in {interaction.guild.name}",
            description=f"Total roles: {len(roles) - 1}", # Subtract 1 to exclude @everyone
            color=discord.Color.blue()
        )
        
        # Add roles to the embed in chunks to avoid hitting the field limit
        chunk_size = 20
        for i in range(0, len(roles), chunk_size):
            chunk = roles[i:i+chunk_size]
            
            # Format the roles
            role_list = []
            for role in chunk:
                if role.is_default():  # Skip @everyone
                    continue
                role_list.append(f"{role.mention} - {len(role.members)} members")
            
            if role_list:
                embed.add_field(
                    name=f"Roles {i+1}-{min(i+chunk_size, len(roles) - 1)}", # Subtract 1 to account for @everyone
                    value="\n".join(role_list),
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)
    
    async def role_info_callback(self, interaction: discord.Interaction, role: discord.Role):
        """Callback for /role info command"""
        # Check if in a guild
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        
        # Create an embed with detailed role information
        embed = discord.Embed(
            title=f"Role Information: {role.name}",
            color=role.color
        )
        
        # Add basic information
        embed.add_field(name="ID", value=role.id, inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Position", value=role.position, inline=True)
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Bot Role", value="Yes" if role.is_bot_managed() else "No", inline=True)
        embed.add_field(name="Integration Role", value="Yes" if role.is_integration() else "No", inline=True)
        embed.add_field(name="Members", value=len(role.members), inline=True)
        embed.add_field(name="Created At", value=discord.utils.format_dt(role.created_at), inline=True)
        
        # Add permissions information
        permissions = []
        for perm, value in role.permissions:
            if value:
                formatted_perm = perm.replace('_', ' ').title()
                permissions.append(f"✅ {formatted_perm}")
        
        if permissions:
            # Split permissions into chunks to avoid hitting the field value limit
            chunk_size = 10
            for i in range(0, len(permissions), chunk_size):
                chunk = permissions[i:i+chunk_size]
                embed.add_field(
                    name="Permissions" if i == 0 else "\u200b",  # Use zero-width space for additional fields
                    value="\n".join(chunk),
                    inline=False
                )
        else:
            embed.add_field(name="Permissions", value="No permissions", inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    async def role_position_callback(self, interaction: discord.Interaction, role: discord.Role, 
                                    position: int, reason: Optional[str] = None):
        """Callback for /role position command"""
        # Check permissions
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
            
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You don't have permission to manage roles.", ephemeral=True)
            return
            
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("I don't have permission to manage roles.", ephemeral=True)
            return
            
        # Check if the role is manageable
        if not role.is_assignable() or role.is_default():
            await interaction.response.send_message("I cannot move this role. It might be the @everyone role or higher than my highest role.", ephemeral=True)
            return
        
        # Validate position
        if position < 1:
            await interaction.response.send_message("Position must be at least 1.", ephemeral=True)
            return
            
        # Get the maximum valid position (excluding @everyone)
        max_position = len(interaction.guild.roles) - 1
        if position > max_position:
            await interaction.response.send_message(f"Position must be at most {max_position}.", ephemeral=True)
            return
        
        # Store original position for the embed
        original_position = role.position
        
        try:
            # Convert the 1-based user-friendly position to the 0-based position used by Discord
            # Also account for the fact that positions are ordered from bottom to top
            actual_position = position
            
            # Move the role
            await role.edit(position=actual_position, reason=f"{reason or 'No reason provided'} (Position changed by {interaction.user})")
            
            # Create an embed with role information
            embed = discord.Embed(
                title="✅ Role Position Changed",
                description=f"Successfully changed position of role {role.mention}",
                color=role.color
            )
            embed.add_field(name="Role", value=role.mention, inline=True)
            embed.add_field(name="Old Position", value=str(original_position), inline=True)
            embed.add_field(name="New Position", value=str(role.position), inline=True)
            embed.add_field(name="Changed by", value=interaction.user.mention, inline=True)
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Role '{role.name}' position changed from {original_position} to {role.position} by {interaction.user} in {interaction.guild.name}")
            
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to change this role's position.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to change role position: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RoleManagementCog(bot))
    logger.info("RoleManagementCog loaded successfully.")
