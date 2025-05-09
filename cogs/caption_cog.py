import discord
from discord.ext import commands
from discord import app_commands, File
from PIL import Image, ImageDraw, ImageFont, ImageSequence
import requests
import io
import os

class CaptionCog(commands.Cog, name="Caption"):
    """Cog for captioning GIFs"""

    def __init__(self, bot):
        self.bot = bot
        # Define preferred font names/paths
        self.preferred_fonts = [
            "impact.ttf",  # Common name for Impact font file
            "Impact",      # Font name Pillow might find if installed system-wide
            os.path.join("FONT", "impact.ttf") # Bundled fallback
        ]

    def _add_text_to_gif(self, image_bytes: bytes, caption_text: str):
        """
        Adds text to each frame of a GIF.
        The text is placed in a white bar at the top of the GIF.
        """
        try:
            gif = Image.open(io.BytesIO(image_bytes))
            frames = []
            
            # Determine font size (e.g., 10% of image height, capped)
            min_font_size = 10
            max_font_size = 50 
            font_size = max(min_font_size, min(max_font_size, int(gif.height * 0.1)))
            
            font = None
            for font_choice in self.preferred_fonts:
                try:
                    font = ImageFont.truetype(font_choice, font_size)
                    print(f"Successfully loaded font: {font_choice}")
                    break 
                except IOError:
                    print(f"Could not load font: {font_choice}. Trying next option.")
            
            if font is None:
                print("All preferred fonts failed to load. Using Pillow's default font.")
                font = ImageFont.load_default()
                # Adjust font size for default font if necessary, as it might render differently.
                # This might require re-calculating text_width and text_height if default font is used.

            text_color = (0, 0, 0)  # Black text
            bar_color = (255, 255, 255)  # White bar

            # Calculate text size and bar height
            # Create a dummy draw object to measure text
            dummy_image = Image.new("RGB", (1, 1))
            dummy_draw = ImageDraw.Draw(dummy_image)
            
            # For Pillow versions >= 10.0.0, use getbbox
            if hasattr(dummy_draw, 'textbbox'):
                text_bbox = dummy_draw.textbbox((0, 0), caption_text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            else: # For older Pillow versions, use textsize (deprecated)
                text_width, text_height = dummy_draw.textsize(caption_text, font=font)

            bar_height = text_height + 20  # Add some padding (10px top, 10px bottom)

            for frame in ImageSequence.Iterator(gif):
                frame = frame.convert("RGBA")
                
                # Create a new image for the frame with space for the text bar
                new_frame_width = frame.width
                new_frame_height = frame.height + bar_height
                
                new_frame = Image.new("RGBA", (new_frame_width, new_frame_height), (0,0,0,0)) # Transparent background for the new area
                
                # Draw the white bar
                draw = ImageDraw.Draw(new_frame)
                draw.rectangle([(0, 0), (new_frame_width, bar_height)], fill=bar_color)
                
                # Paste the original frame below the bar
                new_frame.paste(frame, (0, bar_height))
                
                # Calculate text position (centered in the bar)
                text_x = (new_frame_width - text_width) / 2
                text_y = (bar_height - text_height) / 2
                
                # Add text to the bar
                draw.text((text_x, text_y), caption_text, font=font, fill=text_color)
                
                # Reduce colors to optimize GIF and ensure compatibility
                new_frame_alpha = new_frame.getchannel('A')
                new_frame = new_frame.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
                # If original had transparency, re-apply mask
                if gif.info.get('transparency', None) is not None:
                     new_frame.info['transparency'] = gif.info['transparency'] # Preserve transparency if present
                     # Masking might be needed here if the original GIF had complex transparency
                     # For simplicity, we assume simple transparency or opaque.
                     # If issues arise, more complex alpha compositing might be needed before converting to "P"

                frames.append(new_frame)

            output_gif_bytes = io.BytesIO()
            frames[0].save(
                output_gif_bytes,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=gif.info.get("duration", 100), # Use original duration, default to 100ms
                loop=gif.info.get("loop", 0),           # Use original loop count, default to infinite
                transparency=gif.info.get("transparency", None), # Preserve transparency
                disposal=2 # Important for GIFs with transparency and animation
            )
            output_gif_bytes.seek(0)
            return output_gif_bytes
        except Exception as e:
            print(f"Error in _add_text_to_gif: {e}")
            return None

    @app_commands.command(name="captiongif", description="Captions a GIF with the provided text.")
    @app_commands.describe(
        caption="The text to add to the GIF.",
        url="A URL to a GIF.",
        attachment="An uploaded GIF file."
    )
    async def caption_gif_slash(self, interaction: discord.Interaction, caption: str, url: str = None, attachment: discord.Attachment = None):
        """Slash command to caption a GIF."""
        await interaction.response.defer(thinking=True)

        if not url and not attachment:
            await interaction.followup.send("You must provide either a GIF URL or attach a GIF file.", ephemeral=True)
            return
        if url and attachment:
            await interaction.followup.send("Please provide either a URL or an attachment, not both.", ephemeral=True)
            return

        image_bytes = None
        filename = "captioned_gif.gif"

        if url:
            if not (url.startswith("http://tenor.com/") or url.startswith("https://tenor.com/") or url.endswith(".gif")):
                await interaction.followup.send("The URL must be a direct link to a GIF or a Tenor GIF URL.", ephemeral=True)
                return
            try:
                # Handle Tenor URLs - they often don't directly link to the .gif
                # A more robust way is to use Tenor API if available, or try to find the .gif link in the page
                # For simplicity, we'll assume if it's a tenor URL, we try to get content and hope it's a GIF
                # or that a direct .gif link is provided.
                # A common pattern for Tenor is to find a .mp4 or .gif in the HTML if it's a page URL.
                # This part might need improvement for robust Tenor URL handling.
                
                # Basic check for direct .gif or try to fetch content
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                
                if "gif" not in content_type and url.endswith(".gif"): # If content-type is not gif but url ends with .gif
                    image_bytes = response.content
                elif "gif" in content_type:
                    image_bytes = response.content
                elif "tenor.com" in url: # If it's a tenor URL but not directly a gif
                    # This is a placeholder for more robust Tenor GIF extraction.
                    # Often, the actual GIF is embedded. For now, we'll try to fetch and hope.
                    # A better method would be to parse the HTML for the actual GIF URL.
                    # Or use the Tenor API if the bot has a key.
                    # For now, we'll assume the direct URL is good enough or it's a direct .gif from tenor.
                    # If not, this will likely fail or download HTML.
                    # A quick hack for some tenor URLs: replace .com/view/ with .com/download/ and hope it gives a direct gif
                    if "/view/" in url:
                        potential_gif_url = url.replace("/view/", "/download/") # This is a guess
                        # It's better to inspect the page content for the actual media URL
                        # For now, we'll try the original URL.
                        pass # Keep original URL for now.
                    
                    # Attempt to get the GIF from Tenor page (very basic)
                    if not image_bytes:
                        page_content = response.text
                        import re
                        # Look for a src attribute ending in .gif within an img tag
                        match = re.search(r'<img[^>]+src="([^"]+\.gif)"[^>]*>', page_content)
                        if match:
                            gif_url_from_page = match.group(1)
                            if not gif_url_from_page.startswith("http"): # handle relative URLs if any
                                from urllib.parse import urljoin
                                gif_url_from_page = urljoin(url, gif_url_from_page)
                            
                            response = requests.get(gif_url_from_page, timeout=10)
                            response.raise_for_status()
                            if "gif" in response.headers.get("Content-Type", "").lower():
                                image_bytes = response.content
                        else: # Fallback if no img tag found, try to find a direct media link for tenor
                            # Tenor often uses a specific div for the main GIF content
                            # Example: <div class="Gif" ...><img src="URL.gif" ...></div>
                            # Or sometimes a video tag with a .mp4 that could be converted or a .gif version available
                            # This part is complex without a dedicated Tenor API key and library.
                            # For now, if the initial fetch wasn't a GIF, we might fail here for Tenor pages.
                            await interaction.followup.send("Could not automatically extract GIF from Tenor URL. Please try a direct GIF link.", ephemeral=True)
                            return


                if not image_bytes: # If after all attempts, image_bytes is still None
                     await interaction.followup.send(f"Failed to download or identify GIF from URL: {url}. Content-Type: {content_type}", ephemeral=True)
                     return

            except requests.exceptions.RequestException as e:
                await interaction.followup.send(f"Failed to download GIF from URL: {e}", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"An error occurred while processing the URL: {e}", ephemeral=True)
                return

        elif attachment:
            if not attachment.filename.lower().endswith(".gif") or "image/gif" not in attachment.content_type:
                await interaction.followup.send("The attached file must be a GIF.", ephemeral=True)
                return
            try:
                image_bytes = await attachment.read()
                filename = f"captioned_{attachment.filename}"
            except Exception as e:
                await interaction.followup.send(f"Failed to read attached GIF: {e}", ephemeral=True)
                return
        
        if not image_bytes:
            await interaction.followup.send("Could not load GIF data.", ephemeral=True)
            return

        # Process the GIF
        try:
            captioned_gif_bytes = await self.bot.loop.run_in_executor(None, self._add_text_to_gif, image_bytes, caption)
        except Exception as e: # Catch errors from the executor task
            await interaction.followup.send(f"An error occurred during GIF processing: {e}", ephemeral=True)
            print(f"Error during run_in_executor for _add_text_to_gif: {e}")
            return

        if captioned_gif_bytes:
            discord_file = File(fp=captioned_gif_bytes, filename=filename)
            await interaction.followup.send(file=discord_file)
        else:
            await interaction.followup.send("Failed to caption the GIF. Check bot logs for details.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(CaptionCog(bot))
