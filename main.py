import asyncio
from discord import *
from datetime import datetime
from discord import app_commands
from typing import *
from settings import *
import random
import re


print("Token:", TOKEN)
print("Admins:", ADMINS)

# Customizations
highlight_color: Colour = Colour.from_rgb(0, 255, 255)

# Bot initializing
intents = Intents.default()
bot = Client(intents=intents)
tree = app_commands.CommandTree(bot)


# Helpers
class GuildAgent:

    def as_embed(self) -> Embed:
        embed = Embed(title=self.guild_id, colour=highlight_color)
        embed.add_field(name="General Info", inline=False,
                        value=f'# of Games: {len(self._games)}')
        out_str = '\n'.join(self._games.keys())
        embed.add_field(name='Game Names', inline=False,
                        value=f'```\n{out_str}```')
        return embed

    def __init__(self, guild_id: int) -> None:
        self.guild_id: int = guild_id
        self._games: Dict[str, Game] = {}  # name, game

    def get_game_name(self, game_name: str) -> Union[Game, None]:
        return self._games.get(game_name)

    def get_game_message(self, message: Message):
        return next((game for game in self._games.values() if message == game.ui_message))

    def add_game(self, game: Game, force: bool = False) -> bool:
        if force or game.name not in self._games.keys():
            self._games.update({game.name: game})
            return True
        return False

    async def remove_game(self, game_name: str):
        if game_name in self._games.keys():
            game = self._games.get(game_name)
            self._games.pop(game_name)
            await game.cleanup()
            return True
        return False


class Game:
    REACTIONS = ['\N{THUMBS UP SIGN}']

    def __repr__(self) -> str:
        return f'Game(name={self.name}, num_players={len(self._all_players)}, num_teams={len(self._teams)})'

    def as_embed(self) -> Embed:
        embed = Embed(title=self.name, colour=highlight_color)
        embed.add_field(name="General Info", inline=False,
                        value=f'# of Players: {len(self._all_players)}\n\# of Teams: {len(self._teams)}')
        out_str = '\n'.join(
            [f'{i + 1}: {v.name}' for i, v in enumerate(self._all_players)])
        embed.add_field(name="All Players", inline=False,
                        value=f'```\n{out_str}```')
        for name in self._teams:
            out_str = '\n'.join(
                [f'{i + 1}: {v.name}' for i, v in enumerate(self._teams.get(name))])
            embed.add_field(name=name, inline=False,
                            value=f'```\n{out_str}```')
        embed.add_field(name='Buttons', inline=False, value='```'
                                                            'Join!: join game\n'
                                                            'Leave: leave game\n'
                                                            'Assign: randomize teams'
                                                            '```')
        return embed

    def __init__(self, *, name: str, num_teams: int = 2):
        """Holds information about a specific game

        Args:
            name (str): Name of the game
            num_teams (int, optional): Number of teams to initialize with. Defaults to 2.
        """

        # Utilities
        self.name: str = name
        self.owner: Member = None
        self.thread: Thread = None  # Reference to thread
        self.ui_message: Message = None  # Reference to UI window in thread

        # Game Variables
        self._all_players: List[Member] = []
        self._teams: Dict[str, List[Member]] = {
            f'Team {i + 1}': [] for i in range(num_teams)}

    async def cleanup(self):
        try:
            await self.thread.delete()
        except NotFound as e:  # Thread may have been manually deleted
            pass
        del self

    def add_player(self, player: Member) -> bool:
        if player not in self._all_players:
            self._all_players.append(player)
            return True
        return False

    def remove_player(self, player: Member) -> bool:
        if player in self._all_players:
            self._all_players.remove(player)
            active_team = next(
                (self._teams[team_name] for team_name in self._teams if player in self._teams[team_name]), None)
            if active_team is not None:
                active_team.remove(player)
            return True
        return False

    def randomize_teams(self) -> List[Member]:
        num_players = len(self._all_players)
        num_teams = len(self._teams)
        if num_players == 0:
            return []
        team_size = num_teams // num_players
        if team_size > num_players:
            return []

        copy_players = self._all_players.copy()
        for team_name in self._teams:
            self._teams[team_name].clear()
            for _ in range(team_size):
                player = random.choice(copy_players)
                copy_players.remove(player)
                self._teams[team_name].append(player)
        return copy_players


class GameButtons(ui.View):

    def __init__(self):
        super().__init__()

    @ui.button(label="Join!", row=0, style=ButtonStyle.success)
    async def join_button_callback(self, interaction: Interaction, button: Button):
        guild_agent = Utils.connections.get(interaction.guild_id)
        user = interaction.user
        if guild_agent is not None:
            game = guild_agent.get_game_message(message=interaction.message)
            if game is not None:
                success = game.add_player(user)
                if success:
                    await game.ui_message.edit(embed=game.as_embed())
                    await interaction.channel.send(f'{user.name} has joined')
                else:
                    await interaction.channel.send(f'Failed to add {user.name}')
                await interaction.response.defer()

    @ui.button(label="Leave", row=0, style=ButtonStyle.danger)
    async def leave_button_callback(self, interaction: Interaction, button: Button):
        guild_agent = Utils.connections.get(interaction.guild_id)
        user = interaction.user
        if guild_agent is not None:
            game = guild_agent.get_game_message(message=interaction.message)
            if game is not None:
                success = game.remove_player(user)
                if success:
                    await game.ui_message.edit(embed=game.as_embed())
                    await interaction.channel.send(f'{user.name} has left')
                else:
                    await interaction.channel.send(f'Failed to remove {user.name}')
                await interaction.response.defer()

    @ui.button(label="Assign", row=0, style=ButtonStyle.primary)
    async def assign_button_callback(self, interaction: Interaction, button: Button):
        guild_agent = Utils.connections.get(interaction.guild_id)
        if guild_agent is not None:
            game = guild_agent.get_game_message(message=interaction.message)
            if game is not None:
                if interaction.user == game.owner:
                    overflow = game.randomize_teams()
                    await game.ui_message.edit(embed=game.as_embed())
                    await interaction.channel.send(f'Teams randomized')
                else:
                    await interaction.channel.send(f'Only the owner can randomize')
                await interaction.response.defer()


class Utils:
    connections: Dict[int, GuildAgent] = {}

    @staticmethod
    def is_admin(user_id: int) -> bool:
        return user_id in admins

    @classmethod
    def check_guild_agent(cls, guild_id) -> bool:  # Ensure guild agent exists
        if cls.connections.get(guild_id) is None:
            guild_agent = GuildAgent(guild_id=guild_id)
            cls.connections.update({guild_id: guild_agent})
            return True
        return False

    @staticmethod
    # Search for game thread
    def existing_thread(threads: Sequence[Thread], game_name: str) -> Union[Thread, None]:
        return next((t for t in threads if f'TC[{game_name}]' == t.name), None)

    @staticmethod
    async def sendLogs(content: str, command_name: str = None):
        """Sends command name and content to logging server

        Args:
            content (str): content to be sent in log
            command_name (str, optional): command name to be logged. Defaults to None.
        """
        if LOGS_CHANNEL:
            log_channel = bot.get_channel(LOGS_CHANNEL)  # Logs channel
            current_time: str = datetime.now().strftime('%H:%M')
            if command_name is not None:
                output = f'```{command_name} - {current_time}\n{content}```'
            else:
                output = f'```{content} - {current_time}```'
            print(output)
            await log_channel.send(output)


@bot.event
async def on_ready():
    await tree.sync()
    await Utils.sendLogs('TeamCreator ready')
    await bot.change_presence(activity=Activity(type=ActivityType.watching, name=f'for help'))
    print('Bot Ready')


@tree.command(name='help', description='help list')
async def help(interaction: Interaction):
    embed = Embed(title=f'Bot Commands',
                  url='https://www.youtube.com/watch?v=dQw4w9WgXcQ', colour=highlight_color)
    embed.add_field(name='General', inline=False, value='')
    commands_str = '\n'.join(
        [f'**/{cmd.name}**: {cmd.description}' for cmd in tree.get_commands()])
    embed.add_field(name='Team Creator', inline=False, value=commands_str)
    await interaction.response.send_message(embed=embed)


@tree.command(name='invitebot', description='temp')
async def invite_bot(interaction: Interaction):
    if BOT_INVITE_LINK:
        embed = Embed(title=f'Click Me!', url=BOT_INVITE_LINK,
                      colour=highlight_color)
    else:
        embed = Embed(title=f'No Link Found!',
                      colour=highlight_color)
    await interaction.response.send_message(embed=embed)


@tree.command(name='test', description='testing call')
async def test(interaction: Interaction, prompt: str):
    await interaction.response.send_message(content=prompt)


@tree.command(name='gamelist', description='shows all active games')
async def get_all_games(interaction: Interaction):
    guild_id = interaction.guild_id
    # initialize if guild agent doesn't exist yet
    Utils.check_guild_agent(guild_id)
    guild_agent = Utils.connections.get(guild_id)
    await interaction.response.send_message(embed=guild_agent.as_embed())


@tree.command(name='creategame', description='creates a game')
async def create_game(interaction: Interaction, name: str, force: bool = False):
    guild_id = interaction.guild_id
    # initialize if guild agent doesn't exist yet
    Utils.check_guild_agent(guild_id)
    guild_agent = Utils.connections.get(guild_id)

    # Attempt to add a new game
    new_game = Game(name=name)
    new_game.owner = interaction.user
    success = guild_agent.add_game(new_game, force=force)
    if not success:  # Name collision, disregarded if force is True
        await interaction.response.send_message(content=f'Game named {name} already exists')
        return

    # Create a thread for game
    if (thread := Utils.existing_thread(interaction.guild.threads, new_game.name)) is not None:
        await thread.delete()
    new_game.thread = await interaction.channel.create_thread(name=f'TC[{new_game.name}]',
                                                              type=ChannelType.public_thread, auto_archive_duration=60,
                                                              reason='Thread for game')
    new_game.thread.locked = True
    await interaction.response.send_message(embed=Embed(title=f'Game: {new_game.name}', url=new_game.thread.jump_url, colour=highlight_color))

    # Send initial UI
    new_game.ui_message = await new_game.thread.send(embed=new_game.as_embed(), view=GameButtons())


@tree.command(name='endgame', description='ends a game')
async def delete_game(interaction: Interaction, name: str):
    guild_id = interaction.guild_id
    # initialize if guild agent doesn't exist yet
    Utils.check_guild_agent(guild_id)
    guild_agent = Utils.connections.get(guild_id)

    if guild_agent.get_game_name(name) is not None:  # Game exists
        await guild_agent.remove_game(name)
        await interaction.response.send_message(content=f'Game {name} successfully deleted')
    else:  # Game doesn't exist
        await interaction.response.send_message(content=f'Game {name} not found')


@tree.command(name='getthread', description='get a jump url to game thread')
async def get_thread(interaction: Interaction, name: str):
    guild_id = interaction.guild_id

    # initialize if guild agent doesn't exist yet
    Utils.check_guild_agent(guild_id)
    guild_agent = Utils.connections.get(guild_id)
    game = guild_agent.get_game_name(name)

    if game is None:
        await interaction.response.send_message(content=f'Game {name} not found')
    else:
        await interaction.response.send_message(
            embed=Embed(title=f'Game: {game.name}', url=game.thread.jump_url, colour=highlight_color))


bot.run(TOKEN)
