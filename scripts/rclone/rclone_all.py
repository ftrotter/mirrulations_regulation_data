import os
from dotenv import load_dotenv

load_dotenv() #So we can get our passwords from the .env file

dest_dir = os.getenv('MIRRULATIONS_DESTINATION_PATH')
rclone_config_file = os.getenv('RCLONE_CONFIG_FILE')

has_error = False

if not os.path.exists(dest_dir):
    print(f"Error: {dest_dir} does not exist ")
    has_error = True

if not os.path.isfile(rclone_config_file):
    print(f"Error: {rclone_config_file} is not found")
    has_error = True

if has_error:
    print("Crashing due to errors")
    exit()

print(f"Saving data to: {dest_dir} \n using rclone configuration file {rclone_config_file}")

