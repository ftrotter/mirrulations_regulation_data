import os
from dotenv import load_dotenv
import click
import time
import datetime
import sys

# Check for .env file before attempting to load it
env_file_path = os.path.join(os.path.dirname(__file__), '.env')
if not os.path.isfile(env_file_path):
    print(f"Error: .env file not found at {env_file_path}")
    print("Please create a .env file by copying example.env and configuring the required variables:")
    print("  MIRRULATIONS_DESTINATION_PATH")
    print("  RCLONE_CONFIG_FILE")
    sys.exit(1)

load_dotenv(env_file_path) #So we can get our passwords from the .env file


#print(f"Saving data to: {dest_dir} \nUsing rclone configuration file {rclone_config_file}")

#my_command = f"rclone copy myconfig:mirrulations/ {dest_dir} --config {rclone_config_file}"

#print(f"Running: \n\t{my_command}")
#os.system(my_command)


def parse_years(year_str):
    years = []
    for item in year_str.split(','):
        if '-' in item:
            start, end = map(int, item.split('-'))
            years.extend(range(start, end + 1))
        else:
            years.append(int(item))
    return years


def print_and_run_command_array(command_array):

    print("Preparing to run:")
    for this_command in command_array:
        print(f"\t{command_array}")

    if click.confirm('Do you want to run these commands?', default=False):
        for this_command in command_array:
            print(f"Running:\t{this_command}")
            os.system(this_command)
    else:
        print("Not running. Goodbye.")
        exit()




@click.command()
@click.option('--agency', '-a', default='', help="Agency name(s) separated by commas.")
@click.option('--year', '-y', default='', help="Year(s) or range(s) of years separated by commas or dash (e.g., 2010-2015).")
@click.option('--textonly', is_flag=True, help="Flag to indicate if textonly should be True.")
@click.option('--getall', is_flag=True, help="Download all agencies, all years. (WARNING: this could cost a few hundred dollars...)")
@click.option('--transfers', default='', help="How many rclone connections to run at the same time (default is 50)")
@click.option('--docket','-d', default='', help="Download a specific docket id")

def main(agency, year, docket, textonly, getall, transfers ):
    agency_list = [agency.strip() for agency in agency.split(',') if agency.strip()]
    docket_list =  [docket.strip() for docket in docket.split(',') if docket.strip()]
    
    if year:
        year_list = parse_years(year)
    else:
        year_list = []


    run_command(agency_list, year_list, docket_list, textonly, getall, transfers)

def run_command(agency_list, year_list, docket_list, textonly, getall, transfers):
    """A command to generate and run the rclone commands needed to download regulations data from the mirrulations project!"""

    start_time = time.time()

    #How many rclone transfers should we use? We need to figure it out before we build the arguments to rclone that we 
    #Will use on any future command
    transfers_to_use = 50
    if transfers:
        if(transfers.isnumeric()):
            transfers_to_use = transfers
        else:
            print("Non numeric value for transfers argument. confusion. exiting")
            exit()
    checkers_to_use = int(transfers_to_use) * 2

    #these are the rclone commands that we always use
    always_flags = f" --checkers {checkers_to_use} --transfers {transfers_to_use} --log-file 'rclone.log' -P "

    #tracks whether there is a limitation argument
    is_limited = False

    if getall:
        is_enough = True
    else:
        is_enough = False

    if len(agency_list) > 0:
        is_enough = True
        is_limited = True
    else:
        agency_list = [ '*' ]

    if len(year_list) > 0:
        is_enough = True
        is_limited = True
    else:
        year_list = [ '*' ]

    if len(docket_list) > 0:
        is_enough = True
        is_limited = True
    else:
        docket_list = []


    #All 'text only' means is that we are not doing the word documents, pdfs, etc etc.. we just want to the raw text files
    #these come in three flavors... 
    if not textonly:
        included_file_types = ['*']
    else:
        included_file_types = ['*.txt','*.json','*.htm']
        is_limited = True
        is_enough = True

#we either need --getall or we need some other limitation
    #we are not just going to download everything without some indication that we should...
    if not is_enough:
        print("If you want to download everything.. pass in the --getall paramater and go to lunch!! \nOtherwise add the --help for a full list of options")
        exit()
    

    #A substantial part of our configuration is contained in rclone configuration file 
    #We need to make sure these exist! 
    dest_dir = os.getenv('MIRRULATIONS_DESTINATION_PATH')
    rclone_config_file = os.getenv('RCLONE_CONFIG_FILE')

    has_error = False

    if dest_dir is None:
        print(f"Error: MIRRULATIONS_DESTINATION_PATH environment variable is not set. Please set it in your .env file")
        has_error = True
    elif not os.path.exists(dest_dir):
        print(f"Error: {dest_dir} does not exist ")
        has_error = True

    if rclone_config_file is None:
        print(f"Error: RCLONE_CONFIG_FILE environment variable is not set. Please set it in your .env file")
        has_error = True
    elif not os.path.isfile(rclone_config_file):
        print(f"Error: {rclone_config_file} is not found")
        has_error = True

    if has_error:
        print("Crashing due to errors")
        exit()

    #If we get here then we have the files we need to proceed.
    #I is possible that junk in the rclone.conf file would keep this from working...
    #This will be the command.. or the prefix for the commands that we try to build later
    base_rclone_command = f"rclone copy myconfig:mirrulations/ {dest_dir} --config {rclone_config_file} {always_flags}"

    if getall:
        if is_limited:
            print(f"You have entered --getall and a filter at the same time. I dont know what to do... so I am not going to do anything. Try --help")
            exit()
        else:
            #If we get here, then shoudl simply download everything.
            #we just run the command with no modification with --include statements
            commands_to_run = [ base_rclone_command ]
            print_and_run_command_array(commands_to_run)
    else:
        #Here we are downloading some subset of the data.. which we will express with one or more --include statements to the rclone command
        commands_to_run = []

        include_these = []
        for this_agency in agency_list:
            for this_year in year_list:
                if this_year != '*':
                    this_year = f"*{this_year}*"
                for this_file_type in included_file_types:
                    # Updated pattern to match new directory structure with raw-data/ and derived-data/
                    include_these.append(f"/*/{this_agency}/{this_year}/**/{this_file_type}")

        # if we are doing dockets.. that is all we are doing
        if len(docket_list) > 0:
            include_these = []

        for this_docket in docket_list:
            # To really have any speed-up.. we also need to narrow by agency. Otherwise.. we will ahve to search for every agency 
            # for the matching docket id.
            # dockets take the form AGENCY-YEAR-ID like the soon to be famous DEA-2024-0059
            docket_string_list = this_docket.split('-')
            agency = docket_string_list.pop(0) # get the first segment.

            for this_file_type in included_file_types:
                # Updated pattern to match new directory structure (both raw-data/ and derived-data/)
                include_these.append(f"/*/{agency}/{this_docket}/**/{this_file_type}")

        this_command = base_rclone_command
        for include_string in include_these:
            this_command += f" --include \"{include_string}\" "

        command_array = [ this_command ]
        print_and_run_command_array(command_array)

    #No matter if we are downloading a portion or everything..
    #We print out how long it took to run.
    end_time = time.time()

    elapsed_time = round(end_time - start_time)
    printable_elapsed_time = str(datetime.timedelta(seconds = elapsed_time))

    print(f"""
Process finished!
    Took {printable_elapsed_time} to finish ( {elapsed_time} seconds )

            """)


if __name__ == "__main__":
    main()
