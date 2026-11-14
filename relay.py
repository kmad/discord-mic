"""Send audio to one Discord voice channel; never uses a user account token."""

import argparse
import asyncio
import getpass
import logging
import os
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parent


def make_audio_source(args):
    import ctypes.util
    import discord

    if not discord.opus.is_loaded():
        library = ctypes.util.find_library("opus")
        if not library:
            raise ValueError("Opus library missing. Install with: brew install opus")
        discord.opus.load_opus(library)
    before = "-nostdin"
    if args.tone:
        before += " -f lavfi"
        audio_input = f"sine=frequency=440:sample_rate=48000:duration={args.seconds}"
    elif args.file:
        before += " -re"
        audio_input = str(args.file.resolve())
    else:
        before += " -f avfoundation"
        audio_input = f":{args.device}"
    # Feed raw PCM to discord.py's own Opus encoder. This avoids sending
    # FFmpeg's Ogg container headers as if they were Opus audio frames.
    return discord.FFmpegPCMAudio(
        audio_input,
        before_options=before,
        options=f"-vn -af {shlex.quote(f'volume={args.volume}')}",
    )


def configure():
    path = ROOT / ".env"
    if path.exists():
        raise ValueError(".env already exists. Edit it locally to change the token or channel.")
    token = getpass.getpass("Discord BOT token (hidden): ").strip()
    channel = input("General voice channel ID (or leave blank to list channels first): ").strip()
    if not token or any(c.isspace() for c in token):
        raise ValueError("Enter a bot token without whitespace.")
    if channel and (not channel.isdecimal() or int(channel) <= 0):
        raise ValueError("Channel ID must be a positive number.")
    # Exclusive creation and restrictive permissions from the first write.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(f"DISCORD_BOT_TOKEN={token}\nDISCORD_VOICE_CHANNEL_ID={channel}\n")
    print("Saved .env locally. Next: uv run relay.py --channels")


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--configure", action="store_true", help="Save bot credentials locally")
    mode.add_argument("--channels", action="store_true", help="List servers and voice channel IDs")
    mode.add_argument("--tone", action="store_true", help="Play a quiet test tone")
    mode.add_argument("--file", type=Path, help="Play a local audio file")
    mode.add_argument("--device", help="Capture a macOS input, e.g. 'BlackHole 2ch'")
    mode.add_argument("--list-devices", action="store_true", help="Ask FFmpeg to list macOS inputs")
    result.add_argument("--channel", type=int, help="Voice channel ID, overriding .env")
    result.add_argument("--volume", type=float, default=0.5, help="Gain from 0 to 1; default 0.5")
    result.add_argument("--seconds", type=int, default=30, help="Test tone duration; default 30 seconds")
    return result


async def relay(args):
    import discord
    import importlib.metadata
    from dotenv import load_dotenv

    if not args.channels:
        dave_version = importlib.metadata.version("davey")
        parts = tuple(int(part) for part in dave_version.split(".")[:2])
        if discord.__version__ == "2.7.1" and parts >= (0, 2):
            raise ValueError("Incompatible davey version for discord.py 2.7.1. Run: uv sync")
        print(f"Voice libraries: discord.py={discord.__version__}, davey={dave_version}")

    load_dotenv(ROOT / ".env")
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("No bot token. Run: uv run relay.py --configure")
    channel_id = args.channel
    if not args.channels:
        channel_id = channel_id or int(os.environ.get("DISCORD_VOICE_CHANNEL_ID") or "0")
        if channel_id <= 0:
            raise ValueError("Run --channels, then pass --channel ID or set DISCORD_VOICE_CHANNEL_ID in .env.")
        if not shutil.which("ffmpeg"):
            raise ValueError("FFmpeg is required for playback: brew install ffmpeg")
        if args.file and not args.file.is_file():
            raise ValueError(f"Audio file does not exist: {args.file}")

    class RelayClient(discord.Client):
        started = False
        failure = None

        async def on_voice_state_update(self, member, before, after):
            if member.id == self.user.id and after.channel:
                print(f"Bot voice state: self_muted={after.self_mute}, "
                      f"server_muted={after.mute}, self_deafened={after.self_deaf}, "
                      f"server_deafened={after.deaf}")
                if after.mute:
                    print("Bot is SERVER MUTED. A server moderator must unmute it in Discord.")

        async def on_ready(self):
            if self.started:
                return
            self.started = True
            voice = None
            source = None
            try:
                print(f"Connected as bot: {self.user}")
                if args.channels:
                    for guild in self.guilds:
                        print(f"Server: {guild.name}")
                        for channel in guild.voice_channels:
                            permissions = channel.permissions_for(guild.me)
                            print(f"  {channel.name}: {channel.id} "
                                  f"(view={permissions.view_channel}, connect={permissions.connect}, "
                                  f"speak={permissions.speak})")
                    if not self.guilds:
                        print("No servers found. Invite this bot to kmad first.")
                    return
                channel = self.get_channel(channel_id)
                if not isinstance(channel, discord.VoiceChannel):
                    raise ValueError("Target is not an accessible voice channel. Check --channels.")
                permissions = channel.permissions_for(channel.guild.me)
                if not (permissions.view_channel and permissions.connect and permissions.speak):
                    raise ValueError("Bot needs View Channel, Connect, and Speak permissions.")
                voice = await channel.connect(timeout=30, self_mute=False, self_deaf=False)
                state = channel.guild.me.voice
                if state and state.mute:
                    raise ValueError("Bot is server muted. Unmute xbox in Discord, then retry.")
                # Connection completion can precede the initial DAVE key exchange.
                # Log readiness without exposing session keys or privacy codes.
                connection = voice._connection
                for _ in range(50):
                    if connection.dave_protocol_version == 0 or connection.can_encrypt:
                        break
                    await asyncio.sleep(0.1)
                print(f"Voice encryption: protocol={connection.dave_protocol_version}, "
                      f"ready={connection.can_encrypt}; audio=PCM via native Opus encoder")
                if connection.dave_protocol_version and not connection.can_encrypt:
                    raise ValueError("Discord voice encryption did not become ready. Rejoin and retry.")
                source = make_audio_source(args)
                finished = asyncio.get_running_loop().create_future()
                loop = asyncio.get_running_loop()

                def complete(error):
                    def resolve():
                        if not finished.done():
                            finished.set_result(error)
                    loop.call_soon_threadsafe(resolve)

                voice.play(source, after=complete, application="audio", bitrate=128)
                print(f"Playing in {channel.guild.name} / {channel.name}. Ctrl+C stops.")
                error = await finished
                if error:
                    raise error
                print("Playback finished. If you heard silence, check FFmpeg output and Xbox chat routing.")
            except Exception as error:
                self.failure = error
            finally:
                try:
                    if voice:
                        await voice.disconnect(force=True)
                finally:
                    if source:
                        source.cleanup()
                    await self.close()

    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    client = RelayClient(intents=intents)
    async with client:
        await client.start(token)
    if client.failure:
        raise client.failure


def main():
    args = parser().parse_args()
    if not 0 <= args.volume <= 1:
        raise ValueError("Volume must be between 0 and 1.")
    if args.seconds <= 0:
        raise ValueError("Seconds must be positive.")
    if args.configure:
        configure()
    elif args.list_devices:
        import subprocess
        subprocess.run(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""], check=False)
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        asyncio.run(relay(args))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
