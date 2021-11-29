import logging
import os
import sys
import json
import discord
import asyncio
import boto3
import click

client = discord.Client()


@click.command()
@click.argument('instance_map_file', type=click.Path(exists=True))
def main(instance_map_file: str):
    discord_bot = DiscordBot(instance_map_file, client)
    discord_bot.run()


class DiscordBot:

    def __init__(self, instance_map_file: str, discord_client: discord.Client):
        self.is_running = True

        self.logger = logging.getLogger('DiscordBot')

        self.discord_client = discord_client
        self.discord_channel_name = "minecraft-upper"
        self.discord_channel = None

        # TODO: pull region from environment variables
        aws_region = 'us-west-1'
        self.ec2_client = boto3.client('ec2', region_name=aws_region)
        self.instance_map = {}
        self.load_instance_map(instance_map_file)

    def run(self):
        discord_token = os.environ['AWSDISCORDTOKEN']
        if discord_token:
            self.discord_client.run(discord_token)
        else:
            self.logger.error("Could not find discord token.")

    def load_instance_map(self, instance_map_file: str):
        try:
            with open(instance_map_file, "r") as f:
                instance_map_json = json.load(f)
        except FileNotFoundError as e:
            print(e)
            exit()

        if len(instance_map_json) == 0:
            raise Exception("Empty Instance Map")

        for instance_name, instance_id in instance_map_json.items():
            self.instance_map[instance_name] = self.ec2_client.Instance(instance_id)

    @client.event
    async def on_ready(self):
        print('Logged in as')
        print(self.discord_client.user.name)
        print(self.discord_client.user.id)
        print('------------')
        self.discord_channel = discord.utils.get(
            self.discord_client.get_all_channels(),
            name=self.discord_channel_name
        )

    @client.event
    async def on_message(self, message):
        memberIDs = (member.id for member in message.mentions)
        if all([
            self.discord_client.user.id in memberIDs,
            message.channel.name == self.discord_channel_name
        ]):
            print(message.content)
            target_instance_name = message.content.split()[1]

            if target_instance_name in self.instance_map:
                target_instance = self.instance_map[target_instance_name]
                # TODO: refactor this section to:
                #   - allow the GameMonitor has time to safely shutdown
                #   - have a start up sequence
                if 'stop' in message.content:
                    if turnOffInstance(target_instance):
                        await self.discord_channel.send("AWS Instance stopping")
                    else:
                        await self.discord_channel.send('Error stopping AWS Instance')
                elif 'start' in message.content:
                    if turnOnInstance(target_instance):
                        await self.discord_channel.send('AWS Instance starting')
                    else:
                        await self.discord_channel.send('Error starting AWS Instance')
                elif 'status' in message.content:
                    await self.discord_channel.send('AWS Instance status is: ' + getInstanceState(target_instance))

            else:
                await self.discord_channel.send(f"Could not find {target_instance_name}")


def turnOffInstance(instance):
    try:
        instance.stop(False, False)
        return True
    except Exception as e:
        print(e)
        return False


def turnOnInstance(instance):
    try:
        instance.start()
        return True
    except Exception as e:
        print(e)
        return False


def getInstanceState(instance):
    return instance.state['Name']


if __name__ == '__main__':
    main()
