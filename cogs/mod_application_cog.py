import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncpg
import datetime
import logging
import json
from typing import Optional, List, Dict, Any, Union, Literal, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Application statuses
APPLICATION_STATUS = Literal["PENDING", "APPROVED", "REJECTED", "UNDER_REVIEW"]

# Database table creation query
CREATE_MOD_APPLICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS mod_applications (
    application_id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    submission_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'PENDING',
    reviewer_id BIGINT NULL,
    review_date TIMESTAMPTZ NULL,
    form_data JSONB NOT NULL,
    notes TEXT NULL,
    UNIQUE(guild_id, user_id, status)
);
"""

CREATE_MOD_APPLICATION_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS mod_application_settings (
    guild_id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    log_channel_id BIGINT NULL,
    review_channel_id BIGINT NULL,
    required_role_id BIGINT NULL,
    reviewer_role_id BIGINT NULL,
    custom_questions JSONB NULL,
    cooldown_days INTEGER NOT NULL DEFAULT 30
);
"""

# Default application questions
DEFAULT_QUESTIONS = [
    {
        "id": "age",
        "label": "How old are you?",
        "style": discord.TextStyle.short,
        "required": True,
        "max_length": 10
    },
    {
        "id": "experience",
        "label": "Do you have any previous moderation experience?",
        "style": discord.TextStyle.paragraph,
        "required": True,
        "max_length": 1000
    },
    {
        "id": "time_available",
        "label": "How many hours per week can you dedicate to moderating?",
        "style": discord.TextStyle.short,
        "required": True,
        "max_length": 50
    },
    {
        "id": "timezone",
        "label": "What is your timezone?",
        "style": discord.TextStyle.short,
        "required": True,
        "max_length": 50
    },
    {
        "id": "why_mod",
        "label": "Why do you want to be a moderator?",
        "style": discord.TextStyle.paragraph,
        "required": True,
        "max_length": 1000
    }
]

class ModApplicationModal(ui.Modal):
    """Modal for moderator application form"""

    def __init__(self, cog, questions=None):
        super().__init__(title="Moderator Application")
        self.cog = cog

        # Use default questions if none provided
        questions = questions or DEFAULT_QUESTIONS

        # Add form fields dynamically based on questions
        for q in questions:
            text_input = ui.TextInput(
                label=q["label"],
                style=q["style"],
                required=q.get("required", True),
                max_length=q.get("max_length", 1000),
                placeholder=q.get("placeholder", "")
            )
            # Store the question ID as a custom attribute
            text_input.custom_id = q["id"]
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        # Collect form data
        form_data = {}
        for child in self.children:
            if isinstance(child, ui.TextInput):
                form_data[child.custom_id] = child.value

        # Submit application to database
        success = await self.cog.submit_application(interaction.guild_id, interaction.user.id, form_data)

        if success:
            await interaction.response.send_message(
                "✅ Your moderator application has been submitted successfully! You will be notified when it's reviewed.",
                ephemeral=True
            )

            # Notify staff in the review channel
            await self.cog.notify_new_application(interaction.guild, interaction.user, form_data)
        else:
            await interaction.response.send_message(
                "❌ There was an error submitting your application. You may have an existing application pending review.",
                ephemeral=True
            )

class ApplicationReviewView(ui.View):
    """View for reviewing moderator applications"""

    def __init__(self, cog, application_data):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.application_data = application_data

    @ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="approve_application")
    async def approve_button(self, interaction: discord.Interaction, button: ui.Button):
        """Approve the application"""
        await self.cog.update_application_status(
            self.application_data["application_id"],
            "APPROVED",
            interaction.user.id
        )

        # Update the message
        await interaction.response.edit_message(
            content=f"✅ Application approved by {interaction.user.mention}",
            view=None
        )

        # Notify the applicant
        await self.cog.notify_application_status_change(
            interaction.guild,
            self.application_data["user_id"],
            "APPROVED"
        )

    @ui.button(label="Reject", style=discord.ButtonStyle.red, custom_id="reject_application")
    async def reject_button(self, interaction: discord.Interaction, button: ui.Button):
        """Reject the application"""
        # Show rejection reason modal
        await interaction.response.send_modal(
            RejectionReasonModal(self.cog, self.application_data)
        )

    @ui.button(label="Under Review", style=discord.ButtonStyle.blurple, custom_id="review_application")
    async def review_button(self, interaction: discord.Interaction, button: ui.Button):
        """Mark application as under review"""
        await self.cog.update_application_status(
            self.application_data["application_id"],
            "UNDER_REVIEW",
            interaction.user.id
        )

        # Update the message
        await interaction.response.edit_message(
            content=f"🔍 Application marked as under review by {interaction.user.mention}",
            view=self
        )

        # Notify the applicant
        await self.cog.notify_application_status_change(
            interaction.guild,
            self.application_data["user_id"],
            "UNDER_REVIEW"
        )

class RejectionReasonModal(ui.Modal, title="Rejection Reason"):
    """Modal for providing rejection reason"""

    reason = ui.TextInput(
        label="Reason for rejection",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    def __init__(self, cog, application_data):
        super().__init__()
        self.cog = cog
        self.application_data = application_data

    async def on_submit(self, interaction: discord.Interaction):
        """Handle rejection reason submission"""
        await self.cog.update_application_status(
            self.application_data["application_id"],
            "REJECTED",
            interaction.user.id,
            notes=self.reason.value
        )

        # Update the message
        await interaction.response.edit_message(
            content=f"❌ Application rejected by {interaction.user.mention}",
            view=None
        )

        # Notify the applicant
        await self.cog.notify_application_status_change(
            interaction.guild,
            self.application_data["user_id"],
            "REJECTED",
            reason=self.reason.value
        )

class ModApplicationCog(commands.Cog):
    """Cog for handling moderator applications using Discord forms"""

    def __init__(self, bot):
        self.bot = bot

        # Create the main command group for this cog
        self.modapp_group = app_commands.Group(
            name="modapp",
            description="Moderator application system commands"
        )

        # Register commands
        self.register_commands()

        # Add command group to the bot's tree
        self.bot.tree.add_command(self.modapp_group)

    async def cog_load(self):
        """Setup database tables when cog is loaded"""
        if hasattr(self.bot, 'pg_pool') and self.bot.pg_pool:
            try:
                async with self.bot.pg_pool.acquire() as conn:
                    await conn.execute(CREATE_MOD_APPLICATIONS_TABLE)
                    await conn.execute(CREATE_MOD_APPLICATION_SETTINGS_TABLE)
                logger.info("Moderator application tables created successfully")
            except Exception as e:
                logger.error(f"Error creating moderator application tables: {e}")
        else:
            logger.warning("Database pool not available, skipping table creation")

    def register_commands(self):
        """Register all commands for this cog"""

        # --- Apply Command ---
        apply_command = app_commands.Command(
            name="apply",
            description="Apply to become a moderator for this server",
            callback=self.apply_callback,
            parent=self.modapp_group
        )
        self.modapp_group.add_command(apply_command)

        # --- List Applications Command ---
        list_command = app_commands.Command(
            name="list",
            description="List all moderator applications",
            callback=self.list_applications_callback,
            parent=self.modapp_group
        )
        app_commands.describe(
            status="Filter applications by status"
        )(list_command)
        self.modapp_group.add_command(list_command)

        # --- View Application Command ---
        view_command = app_commands.Command(
            name="view",
            description="View details of a specific application",
            callback=self.view_application_callback,
            parent=self.modapp_group
        )
        app_commands.describe(
            application_id="The ID of the application to view"
        )(view_command)
        self.modapp_group.add_command(view_command)

        # --- Configure Command Group ---
        config_group = app_commands.Group(
            name="configure",
            description="Configure moderator application settings",
            parent=self.modapp_group
        )
        self.modapp_group.add_command(config_group)

        # --- Enable/Disable Command ---
        toggle_command = app_commands.Command(
            name="toggle",
            description="Enable or disable the application system",
            callback=self.toggle_applications_callback,
            parent=config_group
        )
        app_commands.describe(
            enabled="Whether applications should be enabled or disabled"
        )(toggle_command)
        config_group.add_command(toggle_command)

        # --- Set Review Channel Command ---
        review_channel_command = app_commands.Command(
            name="reviewchannel",
            description="Set the channel where new applications will be posted for review",
            callback=self.set_review_channel_callback,
            parent=config_group
        )
        app_commands.describe(
            channel="The channel where applications will be posted for review"
        )(review_channel_command)
        config_group.add_command(review_channel_command)

        # --- Set Log Channel Command ---
        log_channel_command = app_commands.Command(
            name="logchannel",
            description="Set the channel where application activity will be logged",
            callback=self.set_log_channel_callback,
            parent=config_group
        )
        app_commands.describe(
            channel="The channel where application activity will be logged"
        )(log_channel_command)
        config_group.add_command(log_channel_command)

        # --- Set Reviewer Role Command ---
        reviewer_role_command = app_commands.Command(
            name="reviewerrole",
            description="Set the role that can review applications",
            callback=self.set_reviewer_role_callback,
            parent=config_group
        )
        app_commands.describe(
            role="The role that can review applications"
        )(reviewer_role_command)
        config_group.add_command(reviewer_role_command)

        # --- Set Required Role Command ---
        required_role_command = app_commands.Command(
            name="requiredrole",
            description="Set the role required to apply (optional)",
            callback=self.set_required_role_callback,
            parent=config_group
        )
        app_commands.describe(
            role="The role required to apply (or None to allow anyone)"
        )(required_role_command)
        config_group.add_command(required_role_command)

        # --- Set Cooldown Command ---
        cooldown_command = app_commands.Command(
            name="cooldown",
            description="Set the cooldown period between rejected applications",
            callback=self.set_cooldown_callback,
            parent=config_group
        )
        app_commands.describe(
            days="Number of days a user must wait after rejection before applying again"
        )(cooldown_command)
        config_group.add_command(cooldown_command)

    # --- Command Callbacks ---

    async def apply_callback(self, interaction: discord.Interaction):
        """Handle the /apply command"""
        # Check if applications are enabled for this guild
        settings = await self.get_application_settings(interaction.guild_id)
        if not settings or not settings.get("enabled", False):
            await interaction.response.send_message(
                "❌ Moderator applications are currently disabled for this server.",
                ephemeral=True
            )
            return

        # Check if user has the required role (if set)
        required_role_id = settings.get("required_role_id")
        if required_role_id:
            member = interaction.guild.get_member(interaction.user.id)
            if not member or not any(role.id == required_role_id for role in member.roles):
                required_role = interaction.guild.get_role(required_role_id)
                role_name = required_role.name if required_role else "Required Role"
                await interaction.response.send_message(
                    f"❌ You need the {role_name} role to apply for moderator.",
                    ephemeral=True
                )
                return

        # Check if user has a pending or under review application
        has_active_application = await self.check_active_application(interaction.guild_id, interaction.user.id)
        if has_active_application:
            await interaction.response.send_message(
                "❌ You already have an application pending review. Please wait for it to be processed.",
                ephemeral=True
            )
            return

        # Check if user is on cooldown from a rejected application
        on_cooldown, days_left = await self.check_application_cooldown(interaction.guild_id, interaction.user.id, settings.get("cooldown_days", 30))
        if on_cooldown:
            await interaction.response.send_message(
                f"❌ You must wait {days_left} more days before submitting a new application.",
                ephemeral=True
            )
            return

        # Get custom questions if configured, otherwise use defaults
        questions = settings.get("custom_questions", DEFAULT_QUESTIONS)

        # Show the application form
        await interaction.response.send_modal(ModApplicationModal(self, questions))

    async def list_applications_callback(self, interaction: discord.Interaction, status: Optional[str] = None):
        """Handle the /modapp list command"""
        # Check if user has permission to view applications
        if not await self.check_reviewer_permission(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to view applications.",
                ephemeral=True
            )
            return

        # Validate status parameter if provided
        valid_statuses = ["PENDING", "APPROVED", "REJECTED", "UNDER_REVIEW"]
        if status and status.upper() not in valid_statuses:
            await interaction.response.send_message(
                f"❌ Invalid status. Valid options are: {', '.join(valid_statuses)}",
                ephemeral=True
            )
            return

        # Fetch applications from database
        applications = await self.get_applications(interaction.guild_id, status.upper() if status else None)

        if not applications:
            await interaction.response.send_message(
                f"No applications found{f' with status {status.upper()}' if status else ''}.",
                ephemeral=True
            )
            return

        # Create an embed to display the applications
        embed = discord.Embed(
            title=f"Moderator Applications{f' ({status.upper()})' if status else ''}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )

        for app in applications:
            user = self.bot.get_user(app["user_id"]) or f"User ID: {app['user_id']}"
            user_display = user.mention if isinstance(user, discord.User) else user

            # Format submission date
            submission_date = app["submission_date"].strftime("%Y-%m-%d %H:%M UTC")

            # Add field for this application
            embed.add_field(
                name=f"Application #{app['application_id']} - {app['status']}",
                value=f"From: {user_display}\nSubmitted: {submission_date}\nUse `/modapp view {app['application_id']}` to view details",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def view_application_callback(self, interaction: discord.Interaction, application_id: int):
        """Handle the /modapp view command"""
        # Check if user has permission to view applications
        if not await self.check_reviewer_permission(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to view applications.",
                ephemeral=True
            )
            return

        # Fetch application from database
        application = await self.get_application_by_id(application_id)

        if not application or application["guild_id"] != interaction.guild_id:
            await interaction.response.send_message(
                "❌ Application not found.",
                ephemeral=True
            )
            return

        # Get user objects
        applicant = self.bot.get_user(application["user_id"]) or f"User ID: {application['user_id']}"
        applicant_display = applicant.mention if isinstance(applicant, discord.User) else applicant

        reviewer = None
        if application["reviewer_id"]:
            reviewer = self.bot.get_user(application["reviewer_id"]) or f"User ID: {application['reviewer_id']}"
        reviewer_display = reviewer.mention if isinstance(reviewer, discord.User) else reviewer or "None"

        # Create an embed to display the application details
        embed = discord.Embed(
            title=f"Moderator Application #{application_id}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )

        # Add application metadata
        embed.add_field(name="Applicant", value=applicant_display, inline=True)
        embed.add_field(name="Status", value=application["status"], inline=True)
        embed.add_field(name="Submitted", value=application["submission_date"].strftime("%Y-%m-%d %H:%M UTC"), inline=True)

        if application["reviewer_id"]:
            embed.add_field(name="Reviewed By", value=reviewer_display, inline=True)
            embed.add_field(name="Review Date", value=application["review_date"].strftime("%Y-%m-%d %H:%M UTC") if application["review_date"] else "N/A", inline=True)

        # Add application form data
        embed.add_field(name="Application Responses", value="", inline=False)

        form_data = application["form_data"]
        for key, value in form_data.items():
            # Try to find the question label from DEFAULT_QUESTIONS
            question_label = next((q["label"] for q in DEFAULT_QUESTIONS if q["id"] == key), key)
            embed.add_field(name=question_label, value=value, inline=False)

        # Add notes if available
        if application["notes"]:
            embed.add_field(name="Notes", value=application["notes"], inline=False)

        # Create view with action buttons if application is pending or under review
        view = None
        if application["status"] in ["PENDING", "UNDER_REVIEW"]:
            view = ApplicationReviewView(self, application)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def toggle_applications_callback(self, interaction: discord.Interaction, enabled: bool):
        """Handle the /modapp configure toggle command"""
        # Check if user has permission to manage applications
        if not await self.check_admin_permission(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to manage application settings.",
                ephemeral=True
            )
            return

        # Update setting in database
        success = await self.update_application_setting(interaction.guild_id, "enabled", enabled)

        if success:
            status = "enabled" if enabled else "disabled"
            await interaction.response.send_message(
                f"✅ Moderator applications are now {status} for this server.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to update application settings.",
                ephemeral=True
            )

    async def set_review_channel_callback(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Handle the /modapp configure reviewchannel command"""
        # Check if user has permission to manage applications
        if not await self.check_admin_permission(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to manage application settings.",
                ephemeral=True
            )
            return

        # Update setting in database
        success = await self.update_application_setting(interaction.guild_id, "review_channel_id", channel.id)

        if success:
            await interaction.response.send_message(
                f"✅ New applications will now be posted in {channel.mention} for review.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to update application settings.",
                ephemeral=True
            )

    async def set_log_channel_callback(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Handle the /modapp configure logchannel command"""
        # Check if user has permission to manage applications
        if not await self.check_admin_permission(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to manage application settings.",
                ephemeral=True
            )
            return

        # Update setting in database
        success = await self.update_application_setting(interaction.guild_id, "log_channel_id", channel.id)

        if success:
            await interaction.response.send_message(
                f"✅ Application activity will now be logged in {channel.mention}.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to update application settings.",
                ephemeral=True
            )

    async def set_reviewer_role_callback(self, interaction: discord.Interaction, role: discord.Role):
        """Handle the /modapp configure reviewerrole command"""
        # Check if user has permission to manage applications
        if not await self.check_admin_permission(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to manage application settings.",
                ephemeral=True
            )
            return

        # Update setting in database
        success = await self.update_application_setting(interaction.guild_id, "reviewer_role_id", role.id)

        if success:
            await interaction.response.send_message(
                f"✅ Members with the {role.mention} role can now review applications.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to update application settings.",
                ephemeral=True
            )

    async def set_required_role_callback(self, interaction: discord.Interaction, role: Optional[discord.Role] = None):
        """Handle the /modapp configure requiredrole command"""
        # Check if user has permission to manage applications
        if not await self.check_admin_permission(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to manage application settings.",
                ephemeral=True
            )
            return

        # Update setting in database (None means no role required)
        role_id = role.id if role else None
        success = await self.update_application_setting(interaction.guild_id, "required_role_id", role_id)

        if success:
            if role:
                await interaction.response.send_message(
                    f"✅ Members now need the {role.mention} role to apply for moderator.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "✅ Any member can now apply for moderator (no role requirement).",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Failed to update application settings.",
                ephemeral=True
            )

    async def set_cooldown_callback(self, interaction: discord.Interaction, days: int):
        """Handle the /modapp configure cooldown command"""
        # Check if user has permission to manage applications
        if not await self.check_admin_permission(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to manage application settings.",
                ephemeral=True
            )
            return

        # Validate days parameter
        if days < 0 or days > 365:
            await interaction.response.send_message(
                "❌ Cooldown days must be between 0 and 365.",
                ephemeral=True
            )
            return

        # Update setting in database
        success = await self.update_application_setting(interaction.guild_id, "cooldown_days", days)

        if success:
            if days == 0:
                await interaction.response.send_message(
                    "✅ Application cooldown has been disabled. Users can reapply immediately after rejection.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"✅ Users must now wait {days} days after rejection before submitting a new application.",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Failed to update application settings.",
                ephemeral=True
            )

    # --- Database Helper Methods ---

    async def submit_application(self, guild_id: int, user_id: int, form_data: Dict[str, str]) -> bool:
        """Submit a new application to the database"""
        if not hasattr(self.bot, 'pg_pool') or not self.bot.pg_pool:
            logger.error("Database pool not available")
            return False

        try:
            async with self.bot.pg_pool.acquire() as conn:
                # Convert form_data to JSON string
                form_data_json = json.dumps(form_data)

                # Insert application into database
                await conn.execute("""
                    INSERT INTO mod_applications (guild_id, user_id, form_data)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, user_id, status)
                    WHERE status IN ('PENDING', 'UNDER_REVIEW')
                    DO NOTHING
                """, guild_id, user_id, form_data_json)

                # Check if the insert was successful by querying for the application
                result = await conn.fetchrow("""
                    SELECT application_id FROM mod_applications
                    WHERE guild_id = $1 AND user_id = $2 AND status IN ('PENDING', 'UNDER_REVIEW')
                """, guild_id, user_id)

                return result is not None
        except Exception as e:
            logger.error(f"Error submitting application: {e}")
            return False

    async def get_applications(self, guild_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all applications for a guild, optionally filtered by status"""
        if not hasattr(self.bot, 'pg_pool') or not self.bot.pg_pool:
            logger.error("Database pool not available")
            return []

        try:
            async with self.bot.pg_pool.acquire() as conn:
                if status:
                    # Filter by status
                    rows = await conn.fetch("""
                        SELECT * FROM mod_applications
                        WHERE guild_id = $1 AND status = $2
                        ORDER BY submission_date DESC
                    """, guild_id, status)
                else:
                    # Get all applications
                    rows = await conn.fetch("""
                        SELECT * FROM mod_applications
                        WHERE guild_id = $1
                        ORDER BY submission_date DESC
                    """, guild_id)

                # Convert rows to dictionaries and parse form_data JSON
                applications = []
                for row in rows:
                    app = dict(row)
                    app["form_data"] = json.loads(app["form_data"])
                    applications.append(app)

                return applications
        except Exception as e:
            logger.error(f"Error getting applications: {e}")
            return []

    async def get_application_by_id(self, application_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific application by ID"""
        if not hasattr(self.bot, 'pg_pool') or not self.bot.pg_pool:
            logger.error("Database pool not available")
            return None

        try:
            async with self.bot.pg_pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM mod_applications
                    WHERE application_id = $1
                """, application_id)

                if not row:
                    return None

                # Convert row to dictionary and parse form_data JSON
                application = dict(row)
                application["form_data"] = json.loads(application["form_data"])

                return application
        except Exception as e:
            logger.error(f"Error getting application by ID: {e}")
            return None

    async def update_application_status(self, application_id: int, status: APPLICATION_STATUS, reviewer_id: int, notes: Optional[str] = None) -> bool:
        """Update the status of an application"""
        if not hasattr(self.bot, 'pg_pool') or not self.bot.pg_pool:
            logger.error("Database pool not available")
            return False

        try:
            async with self.bot.pg_pool.acquire() as conn:
                # Update application status
                await conn.execute("""
                    UPDATE mod_applications
                    SET status = $1, reviewer_id = $2, review_date = CURRENT_TIMESTAMP, notes = $3
                    WHERE application_id = $4
                """, status, reviewer_id, notes, application_id)

                return True
        except Exception as e:
            logger.error(f"Error updating application status: {e}")
            return False

    async def get_application_settings(self, guild_id: int) -> Dict[str, Any]:
        """Get application settings for a guild"""
        if not hasattr(self.bot, 'pg_pool') or not self.bot.pg_pool:
            logger.error("Database pool not available")
            return {"enabled": False}  # Default settings

        try:
            async with self.bot.pg_pool.acquire() as conn:
                # Check if settings exist for this guild
                row = await conn.fetchrow("""
                    SELECT * FROM mod_application_settings
                    WHERE guild_id = $1
                """, guild_id)

                if not row:
                    # Create default settings
                    await conn.execute("""
                        INSERT INTO mod_application_settings (guild_id)
                        VALUES ($1)
                    """, guild_id)

                    # Return default settings
                    return {
                        "guild_id": guild_id,
                        "enabled": True,
                        "log_channel_id": None,
                        "review_channel_id": None,
                        "required_role_id": None,
                        "reviewer_role_id": None,
                        "custom_questions": None,
                        "cooldown_days": 30
                    }

                # Convert row to dictionary and parse custom_questions JSON if it exists
                settings = dict(row)
                if settings["custom_questions"]:
                    settings["custom_questions"] = json.loads(settings["custom_questions"])

                return settings
        except Exception as e:
            logger.error(f"Error getting application settings: {e}")
            return {"enabled": False}  # Default settings on error

    async def update_application_setting(self, guild_id: int, setting_key: str, setting_value: Any) -> bool:
        """Update a specific application setting for a guild"""
        if not hasattr(self.bot, 'pg_pool') or not self.bot.pg_pool:
            logger.error("Database pool not available")
            return False

        try:
            async with self.bot.pg_pool.acquire() as conn:
                # Check if settings exist for this guild
                exists = await conn.fetchval("""
                    SELECT COUNT(*) FROM mod_application_settings
                    WHERE guild_id = $1
                """, guild_id)

                if not exists:
                    # Create default settings first
                    await conn.execute("""
                        INSERT INTO mod_application_settings (guild_id)
                        VALUES ($1)
                    """, guild_id)

                # Special handling for JSON fields
                if setting_key == "custom_questions" and setting_value is not None:
                    setting_value = json.dumps(setting_value)

                # Update the specific setting
                query = f"""
                    UPDATE mod_application_settings
                    SET {setting_key} = $1
                    WHERE guild_id = $2
                """
                await conn.execute(query, setting_value, guild_id)

                return True
        except Exception as e:
            logger.error(f"Error updating application setting: {e}")
            return False

    async def check_active_application(self, guild_id: int, user_id: int) -> bool:
        """Check if a user has an active application (pending or under review)"""
        if not hasattr(self.bot, 'pg_pool') or not self.bot.pg_pool:
            logger.error("Database pool not available")
            return False

        try:
            async with self.bot.pg_pool.acquire() as conn:
                # Check for active applications
                result = await conn.fetchval("""
                    SELECT COUNT(*) FROM mod_applications
                    WHERE guild_id = $1 AND user_id = $2 AND status IN ('PENDING', 'UNDER_REVIEW')
                """, guild_id, user_id)

                return result > 0
        except Exception as e:
            logger.error(f"Error checking active application: {e}")
            return False

    async def check_application_cooldown(self, guild_id: int, user_id: int, cooldown_days: int) -> Tuple[bool, int]:
        """Check if a user is on cooldown from a rejected application
        Returns (on_cooldown, days_left)
        """
        if cooldown_days <= 0:
            return False, 0

        if not hasattr(self.bot, 'pg_pool') or not self.bot.pg_pool:
            logger.error("Database pool not available")
            return False, 0

        try:
            async with self.bot.pg_pool.acquire() as conn:
                # Get the most recent rejected application
                result = await conn.fetchrow("""
                    SELECT review_date FROM mod_applications
                    WHERE guild_id = $1 AND user_id = $2 AND status = 'REJECTED'
                    ORDER BY review_date DESC
                    LIMIT 1
                """, guild_id, user_id)

                if not result:
                    return False, 0

                # Calculate days since rejection
                review_date = result["review_date"]
                days_since = (datetime.datetime.now(datetime.timezone.utc) - review_date).days

                # Check if still on cooldown
                if days_since < cooldown_days:
                    days_left = cooldown_days - days_since
                    return True, days_left

                return False, 0
        except Exception as e:
            logger.error(f"Error checking application cooldown: {e}")
            return False, 0

    async def check_reviewer_permission(self, guild_id: int, user_id: int) -> bool:
        """Check if a user has permission to review applications"""
        # Get the guild object
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False

        # Get the member object
        member = guild.get_member(user_id)
        if not member:
            return False

        # Check if user is an administrator
        if member.guild_permissions.administrator:
            return True

        # Check if user is the guild owner
        if guild.owner_id == user_id:
            return True

        # Check if user has the reviewer role
        settings = await self.get_application_settings(guild_id)
        reviewer_role_id = settings.get("reviewer_role_id")

        if reviewer_role_id:
            return any(role.id == reviewer_role_id for role in member.roles)

        # Default to requiring administrator if no reviewer role is set
        return False

    async def check_admin_permission(self, guild_id: int, user_id: int) -> bool:
        """Check if a user has permission to manage application settings"""
        # Get the guild object
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False

        # Get the member object
        member = guild.get_member(user_id)
        if not member:
            return False

        # Check if user is an administrator
        if member.guild_permissions.administrator:
            return True

        # Check if user is the guild owner
        if guild.owner_id == user_id:
            return True

        # Only administrators and the guild owner can manage settings
        return False

    async def notify_new_application(self, guild: discord.Guild, user: discord.User, form_data: Dict[str, str]) -> None:
        """Notify staff about a new application"""
        # Get application settings
        settings = await self.get_application_settings(guild.id)
        review_channel_id = settings.get("review_channel_id")

        if not review_channel_id:
            return

        # Get the review channel
        review_channel = guild.get_channel(review_channel_id)
        if not review_channel:
            return

        # Get the application ID
        application = None
        try:
            async with self.bot.pg_pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT application_id FROM mod_applications
                    WHERE guild_id = $1 AND user_id = $2 AND status = 'PENDING'
                    ORDER BY submission_date DESC
                    LIMIT 1
                """, guild.id, user.id)

                if row:
                    application = dict(row)
        except Exception as e:
            logger.error(f"Error getting application ID for notification: {e}")
            return

        if not application:
            return

        # Create an embed for the notification
        embed = discord.Embed(
            title="New Moderator Application",
            description=f"{user.mention} has submitted a moderator application.",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )

        # Add user info
        embed.set_author(name=f"{user.name}", icon_url=user.display_avatar.url)
        embed.add_field(name="User ID", value=user.id, inline=True)
        embed.add_field(name="Application ID", value=application["application_id"], inline=True)

        # Add a preview of the application (first few questions)
        preview_questions = 2  # Number of questions to show in preview
        question_count = 0

        for key, value in form_data.items():
            if question_count >= preview_questions:
                break

            # Try to find the question label from DEFAULT_QUESTIONS
            question_label = next((q["label"] for q in DEFAULT_QUESTIONS if q["id"] == key), key)

            # Truncate long answers
            if len(value) > 100:
                value = value[:97] + "..."

            embed.add_field(name=question_label, value=value, inline=False)
            question_count += 1

        # Add view details button
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="View Full Application",
            style=discord.ButtonStyle.primary,
            custom_id=f"view_application_{application['application_id']}"
        ))

        # Send the notification
        try:
            await review_channel.send(
                content=f"📝 New moderator application from {user.mention}",
                embed=embed,
                view=view
            )
        except Exception as e:
            logger.error(f"Error sending application notification: {e}")

    async def notify_application_status_change(self, guild: discord.Guild, user_id: int, status: APPLICATION_STATUS, reason: Optional[str] = None) -> None:
        """Notify the applicant about a status change"""
        # Get the user
        user = self.bot.get_user(user_id)
        if not user:
            try:
                user = await self.bot.fetch_user(user_id)
            except:
                logger.error(f"Could not fetch user {user_id} for application notification")
                return

        # Create the notification message
        if status == "APPROVED":
            title = "🎉 Application Approved!"
            description = "Congratulations! Your moderator application has been approved."
            color = discord.Color.green()
        elif status == "REJECTED":
            title = "❌ Application Rejected"
            description = "We're sorry, but your moderator application has been rejected."
            if reason:
                description += f"\n\nReason: {reason}"
            color = discord.Color.red()
        elif status == "UNDER_REVIEW":
            title = "🔍 Application Under Review"
            description = "Your moderator application is now being reviewed by our team."
            color = discord.Color.gold()
        else:
            return  # Don't notify for other statuses

        # Create an embed for the notification
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now()
        )

        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        # Try to send a DM to the user
        try:
            await user.send(embed=embed)
        except Exception as e:
            logger.error(f"Error sending application status notification to user {user_id}: {e}")

            # If DM fails, try to log it
            settings = await self.get_application_settings(guild.id)
            log_channel_id = settings.get("log_channel_id")

            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(f"⚠️ Failed to send application status notification to {user.mention}. They may have DMs disabled.")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle custom interactions like view application buttons"""
        if not interaction.data or not interaction.data.get("custom_id"):
            return

        custom_id = interaction.data["custom_id"]

        # Handle view application button
        if custom_id.startswith("view_application_"):
            try:
                application_id = int(custom_id.split("_")[2])

                # Check if user has permission to view applications
                if not await self.check_reviewer_permission(interaction.guild_id, interaction.user.id):
                    await interaction.response.send_message(
                        "❌ You don't have permission to view applications.",
                        ephemeral=True
                    )
                    return

                # Fetch application from database
                application = await self.get_application_by_id(application_id)

                if not application or application["guild_id"] != interaction.guild_id:
                    await interaction.response.send_message(
                        "❌ Application not found.",
                        ephemeral=True
                    )
                    return

                # Call the view application callback
                await self.view_application_callback(interaction, application_id)
            except ValueError:
                pass  # Invalid application ID format
            except Exception as e:
                logger.error(f"Error handling view application button: {e}")
                await interaction.response.send_message(
                    "❌ An error occurred while processing your request.",
                    ephemeral=True
                )

async def setup(bot: commands.Bot):
    await bot.add_cog(ModApplicationCog(bot))