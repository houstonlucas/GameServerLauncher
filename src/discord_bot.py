import logging
import os
import sys
import json
import time
from typing import Dict

import discord
import asyncio
import boto3
import click

from src.constants import RESPONSE_PATH, REQUEST_PATH
from src.utils import Timer, json_to_file, json_from_file

discord_client = discord.Client()


@click.command()
@click.argument('config_file', type=click.Path(exists=True))
def main(config_file: str):
    discord_bot = DiscordBot(config_file, discord_client)
    discord_bot.run()


class DiscordBot:

    def __init__(self, config_file: str, discord_client_: discord.Client):
        self.is_running = False

        # Load configuration
        self.config = json_from_file(config_file)

        self.logger = logging.getLogger(self.config['logger_name'])

        # Discord variables
        self.discord_client = discord_client_
        self.discord_channel_name = self.config['discord_channel_name']
        self.discord_channel = None

        #
        # TODO: pull region from environment variables
        aws_region = 'us-west-1'
        self.ec2_client = boto3.client('ec2', region_name=aws_region)
        self.instance_map = {}
        self.load_instance_map()

    def run(self):
        self.is_running = True
        discord_token = os.environ['AWSDISCORDTOKEN']
        if discord_token:
            self.discord_client.run(discord_token)
        else:
            self.logger.error("Could not find discord token.")

    def load_instance_map(self):
        instance_map_json = {}
        try:
            instance_map_json = json_from_file(self.config['instance_map_file'])
        except FileNotFoundError as e:
            self.logger.error(e)
            exit()

        if len(instance_map_json) == 0:
            raise Exception("Empty Instance Map")

        entry: Dict
        for entry in instance_map_json:
            instance_name = entry['instance_name']
            instance_id = entry['instance_id']
            entry["instance"] = self.ec2_client.Instance(instance_id)
            self.instance_map[instance_name] = entry

    '''
    This function passes messages to the desired instance via 
    '''
    def send_message_to_instance(self, instance, message):
        # This function takes
        # TODO: add usr_name & ip to config
        usr_name = 'ubuntu'
        ip = instance

        remote_request = f'{usr_name}@{ip}:{REQUEST_PATH}'
        remote_response = f'{usr_name}@{ip}:{RESPONSE_PATH}'
        pem_file = self.config['pem_path']

        json_request = {'message': message}
        json_to_file(json_request, REQUEST_PATH)
        os.popen(f"scp -i {pem_file}  {remote_request}")

        # Wait for response
        json_response = None
        response_timer = Timer(30)
        while not response_timer.expired:
            os.popen(f"scp -i {pem_file} {remote_response} {RESPONSE_PATH}")
            if os.path.exists(RESPONSE_PATH):
                # Response received
                json_response = json_from_file(RESPONSE_PATH)
                break
            time.sleep(1)

        if json_response is not None:
            return json_response['message']
        else:
            return "No response was received from instance."
            # TODO: shutdown the instance out of caution.

    @discord_client.event
    async def on_ready(self):
        print('Logged in as')
        print(self.discord_client.user.name)
        print(self.discord_client.user.id)
        print('------------')
        self.discord_channel = discord.utils.get(
            self.discord_client.get_all_channels(),
            name=self.discord_channel_name
        )

    @discord_client.event
    async def on_message(self, message: discord.Message):
        if all([
            self.discord_client.user.id in (member.id for member in message.mentions),
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
