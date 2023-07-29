import os
from dotenv import load_dotenv
import click

load_dotenv() #So we can get our passwords from the .env file



#print(f"Saving data to: {dest_dir} \nUsing rclone configuration file {rclone_config_file}")

#my_command = f"rclone copy myconfig:mirrulations/ {dest_dir} --config {rclone_config_file} --s3-requester-pays"

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
@click.option('--all', is_flag=True, help="Download all agencies, all years. (WARNING: this could cost a few hundred dollars...)")

def main(agency, year, textonly, all ):
    agency_list = [agency.strip() for agency in agency.split(',') if agency.strip()]
    
    if year:
        year_list = parse_years(year)
    else:
        year_list = []

    run_command(agency_list, year_list, textonly, all)

def run_command(agency_list, year_list, textonly, all):
    """A command to generate and run the rclone commands needed to download regulations data from the mirrulations project!"""
    #print("Agency: ", agency_list)
    #print("Year(s): ", year_list)
    #print("Textonly: ", textonly)
    #print("All: ", all)

    always_flags = " --s3-requester-pays --progress --checkers 100 --transfers 50"


    if all:
        is_enough = True
    else:
        is_enough = False

    inlude_statements = []

    if len(agency_list) > 0:
        is_enough = True
    else:
        agency_list = [ '*' ]

    if len(year_list) > 0:
        is_enough = True
    else:
        year_list = [ '*' ]

    if not is_enough:
        print("If you want to download everything.. pass in the --all paramater and go to lunch!! \nOtherwise add the --help for a full list of options")
    
    if not textonly:
        included_file_types = ['*']
    else:
        included_file_types = ['*.txt','*.json','*.htm']


    dest_dir = os.getenv('MIRRULATIONS_DATA_PATH')
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

    if all:
        commands_to_run = [ f"rclone copy myconfig:mirrulations/ {dest_dir} --config {rclone_config_file} {always_flags}" ]
        print_and_run_command_array(commands_to_run)

    commands_to_run = []

    if False:
    #if is_filter_agency and is_filter_year and textonly:
        include_these = []
        for this_agency in agency_list:
            #For each agency make the directory for that agency 
            commands_to_run.append(f"mkdir -p {dest_dir}/{this_agency}")
            for this_year in year_list:
                for this_file_type in text_file_types:
                    include_these.append(f"/{this_agency}/*{this_year}*/**/*.{this_file_type}")
                    
        this_command = f"rclone copy myconfig:mirrulations/ {dest_dir} --config {rclone_config_file} {always_flags} "
        for include_string in include_these:
            this_command += f"--include \"{include_string}\""

    include_these = []
    for this_agency in agency_list:
        for this_year in year_list:
            if this_year != '*':
                this_year = f"*{this_year}*"
            for this_file_type in included_file_types:
                include_these.append(f"/{this_agency}/{this_year}/**/{this_file_type}")

    this_command = f"rclone copy myconfig:mirrulations/ {dest_dir} --config {rclone_config_file} {always_flags}"
    for include_string in include_these:
        this_command += f" --include \"{include_string}\" "

    command_array = [ this_command ]
    print_and_run_command_array(command_array)




if __name__ == "__main__":
    main()
