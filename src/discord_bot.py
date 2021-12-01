import logging
import os
import sys
import json
import time
from typing import Dict, Union

import discord
from discord.ext import commands
import asyncio
import boto3
import click

from src.constants import RESPONSE_PATH, REQUEST_PATH, CONFIRM_PATH
from src.utils import Timer, json_to_file, json_from_file


@click.command()
@click.argument('config_file', type=click.Path(exists=True))
def main(config_file: str):
    discord_bot = DiscordBot(config_file)

    discord_token = os.environ['AWSDISCORDTOKEN']
    if discord_token:
        discord_bot.run(discord_token)
    else:
        discord_bot.logger.error("Could not find discord token.")
    discord_bot.run(discord_token)


class DiscordBot(commands.Bot):

    def __init__(self, config_file: str, **options):
        # Load configuration
        super().__init__(command_prefix="", **options)
        self.config = json_from_file(config_file)

        self.logger = logging.getLogger(self.config['logger_name'])

        # Discord variables
        self.discord_channel_name = self.config['discord_channel_name']
        self.discord_channel = None

        #
        # TODO: pull region from environment variables
        aws_region = 'us-west-1'
        self.ec2 = boto3.resource('ec2', region_name=aws_region)
        self.instance_map = {}
        self.load_instance_map()

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
            entry["instance"] = self.ec2.Instance(instance_id)
            self.instance_map[instance_name] = entry

    '''
    This function passes messages to the desired instance.
    The function returns a string response passed through from the server.
    If there is a timeout waiting for a response the function returns None
    '''
    def send_message_to_instance(self, instance_name, message) -> Union[str, None]:
        # This function takes
        # TODO: add usr_name & ip to config
        usr_name = self.instance_map[instance_name]['user_name']
        ip = self.instance_map[instance_name]['instance'].public_ip_address
        pem_file = self.instance_map[instance_name]['pem_path']

        remote_base = f'{usr_name}@{ip}'

        remote_request = f'{remote_base}:{REQUEST_PATH}'
        remote_response = f'{remote_base}:{RESPONSE_PATH}'
        remote_confirm = f'{remote_base}:{CONFIRM_PATH}'

        # Send the message over with scp
        json_request = {'message': message}
        json_to_file(json_request, REQUEST_PATH)
        os.popen(f"scp -i {pem_file}  {REQUEST_PATH} {remote_request}")

        # Wait for response
        json_response = None
        response_timer = Timer(self.config['response_timeout'])
        while not response_timer.expired:
            os.popen(f"scp -i {pem_file} {remote_response} {RESPONSE_PATH}")
            if os.path.exists(RESPONSE_PATH):
                # Response received
                json_response = json_from_file(RESPONSE_PATH)
                break
            time.sleep(1)

        # Send a confirmation that the response was received
        json_to_file({}, CONFIRM_PATH)
        os.popen(f"scp -i {pem_file} {CONFIRM_PATH} {remote_confirm}")

        if json_response is not None:
            return json_response['message']
        else:
            self.logger.error("No response was received from instance.")
            return None

    def get_instance_name_from_words(self, message_words):
        for instance_name in self.instance_map.keys():
            if instance_name in message_words:
                return instance_name
        return False

    async def on_ready(self):
        print('Logged in as')
        print(self.user.name)
        print(self.user.id)
        print('------------')
        self.discord_channel = discord.utils.get(
            self.get_all_channels(),
            name=self.discord_channel_name
        )

    async def on_message(self, message: discord.Message):
        if all([
            self.user.id in (member.id for member in message.mentions),
            message.channel.name == self.discord_channel_name
        ]):
            print(message.content)
            message_words = message.content.split()
            target_instance_name = self.get_instance_name_from_words(message_words)
            if not target_instance_name:
                await self.discord_channel.send(
                    f'No instance name detected. Available instances: {list(self.instance_map.keys())}'
                )
                self.logger.info('No instance name found in message')
                return

            if target_instance_name in self.instance_map:
                if 'stop' in message_words:
                    await self.stop_instance(target_instance_name, message)
                elif 'start' in message_words:
                    await self.start_instance(target_instance_name, message)
                else:
                    await self.handle_generic_message(target_instance_name, message)
            else:
                await self.discord_channel.send(f'Could not find instance with name: "{target_instance_name}"')

    async def handle_generic_message(self, instance_name, message):
        # Send message and receive response
        response = self.send_message_to_instance(
            instance_name,
            message.content
        )

        # Display response in discord
        await self.discord_channel.send(f'{instance_name} says: {response}')

    async def start_instance(self, instance_name, message):
        instance = self.instance_map[instance_name]['instance']

        # Start the instance up
        if turn_on_instance(instance):
            await self.discord_channel.send('AWS Instance starting')
        else:
            await self.discord_channel.send('Error starting AWS Instance')

        # TODO: Poll for instance start
        time.sleep(15)

        # Pass the instance the startup message and display response in discord
        await self.handle_generic_message(instance_name, message)

    async def stop_instance(self, instance_name, message):
        instance = self.instance_map[instance_name]['instance']

        # Tell the instance to prepare for shutdown and display response in discord
        await self.handle_generic_message(instance_name, message)

        # Turn instance off
        if turn_off_instance(instance):
            await self.discord_channel.send("AWS Instance stopping")
        else:
            await self.discord_channel.send('Error stopping AWS Instance')


def turn_off_instance(instance):
    try:
        instance.stop(False, False)
        return True
    except Exception as e:
        print(e)
        return False


def turn_on_instance(instance):
    try:
        instance.start()
        return True
    except Exception as e:
        print(e)
        return False


def get_instance_state(instance):
    return instance.state['Name']


if __name__ == '__main__':
    main()
