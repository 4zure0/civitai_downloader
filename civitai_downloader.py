import datetime
import json
import shutil
import requests
import os
import urllib
import tqdm

def getFileSize(path) -> int:
    return os.stat(path).st_size

def getCurrentTime() -> str:
    return datetime.datetime.now().strftime("%m-%d-%Y %Hh%Mm%Ss.%f")

def get_working_dir():
    ## Get the absolute path to the script file
    script_path = os.path.abspath(__file__)
    ## Get the directory containing the script file
    script_dir = os.path.dirname(script_path)
    ## Changes working dir to current script_dir
    return script_dir

def print_error():
    print("\nInvalid URL or ID entered. Please double check it to make sure it is correct.")

def extract_id(url: str) -> str: # returns model id from a url
    start_index = url.find("models/")
    model_id = ""
    if start_index == -1: return None
    for c_index in range(start_index+len("models/"), len(url)):
        if url[c_index] == '/': break
        else: model_id += url[c_index]
    return model_id

def get_metadata(model_id: str, civitai_token = None) -> dict: # returns metadata from civitai API
    # URL format: https://civitai.com/api/v1/models/
    headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.civitai.com/',
    'Content-Type': 'application/json'
    }
    if civitai_token is not None:
        headers['Authorization'] = f'Basic {civitai_token}'
    queryPage = f'https://civitai.com/api/v1/models/{model_id}'
    r = requests.get(queryPage, headers=headers)
    if str(r.status_code) == '200': # Not sure if it gets returned as str or int
        try:
            jsonResponse = r.json()
            return jsonResponse
        except Exception as err:
            return None
    else:
        return str(r.status_code)

def write_json(metadata: dict, updated_metadata = True, backup_metadata = True, models_folder = "models") -> bool: # Returns True for success
    not_allowed_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\t', '\n']

    modelId = metadata["id"]
    modelName = metadata["name"]
    modelType = metadata["type"]
    print(
        f"Starting processing of metadata for model {modelName} (id: {modelId})")

    try:
        modelName = ''.join(c for c in modelName if c not in not_allowed_chars)
        dirPath = f"{models_folder}/{modelType}/{modelName} - id {modelId}"

        if updated_metadata or not os.path.exists(dirPath):
            if not os.path.exists(dirPath):
                os.makedirs(dirPath)
            metadataPath = os.path.join(dirPath, f"metadata.json")

            # Backups existing metadata file. Might cause bloating, will improve it eventually.
            if backup_metadata:
                # Checks if json file exists
                if os.path.exists(metadataPath):
                    metadataBackupDir = os.path.join(dirPath, f"metadata_backup")
                    newFilePath = os.path.join(metadataBackupDir, f"{getCurrentTime()} - metadata.json")
                    # Create backup dir if needed
                    if not os.path.exists(metadataBackupDir): os.makedirs(metadataBackupDir)
                    shutil.copy(metadataPath, newFilePath) # Copy file
            
            # Write metadata.json and shortcut to model page on CivitAI site
            with open(metadataPath, "w", encoding="utf-8") as metadataFile:
                json.dump(metadata, metadataFile, indent=4)
            with open(os.path.join(f'{dirPath}', f'{modelName} - id {modelId}.url'), 'w', encoding="utf-8") as shortcutFile:
                shortcutFile.write(
                    f"[InternetShortcut]\nURL=https://civitai.com/models/{modelId}")
        return True
    except: return False

def download_models(metadata: dict, skip_duplicates = True, models_folder = "models", use_subfolder = False):
    modelId = metadata["id"]
    modelName = metadata["name"]
    modelType = metadata["type"]

    not_allowed_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\t', '\n']
    modelName = ''.join(c for c in modelName if c not in not_allowed_chars)
    if use_subfolder:
        dirPath = f"{models_folder}/{modelType}/{modelName} - id {modelId}/files"
    else:
        dirPath = f"{models_folder}/{modelType}/{modelName} - id {modelId}"

    if not os.path.exists(dirPath): os.makedirs(dirPath)
    try:
        for model_version in metadata['modelVersions']: # iter through all model versions
            for model_file in model_version['files']:# not sure if one version can have multiple files, but civitai return it as a list so...

                file_path = os.path.join(dirPath, model_file['name'])
                
                # No renaming function for duplicate models yet.
                # I will probably just add a hash check later instead of
                # just renaming it, since this could use a lot of space
                if skip_duplicates:
                    if os.path.exists(file_path): continue # go to next file if already downloaded

                print(f"Downloading model file for {modelName}\nURL: {model_file['downloadUrl']}")

                r = requests.get(model_file['downloadUrl'], stream=True)
                total_size_in_bytes= int(r.headers.get('content-length', 0))
                block_size = 1024 #1 Kibibyte
                progress_bar = tqdm.tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True)
                with open(file_path, 'wb') as f:
                    for data in r.iter_content(block_size):
                        progress_bar.update(len(data))
                        f.write(data)

    except Exception as err: print(err)

def download_imgs(metadata: dict, skip_duplicates = True, redownload_corrupted = True, models_folder = "models"):
    ## IMAGE DOWNLOADER
    # This code is a fucking mess. Feel free to improve it :)
    # Some ideas for improvement:
    # - Separate the for loops into another function
    # - Use this function to only call the actual download part
    # - Return a status_code
    # - Handle status_code accordingly in the other function (ignoring `404`, retrying `500` etc)
    # - Store failed urls and other data in a json on the root folder

    not_allowed_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\t', '\n']

    modelId = metadata["id"]
    modelName = metadata["name"]
    modelType = metadata["type"]

    modelName = ''.join(c for c in modelName if c not in not_allowed_chars)
    previewsPath = f"{models_folder}/{modelType}/{modelName} - id {modelId}/previews" 
    if not os.path.exists(previewsPath): os.makedirs(previewsPath)
    
    # Loops through all versions of the model
    for modelVersion in metadata["modelVersions"]:
        # Loops through all images in each version
        for image in modelVersion["images"]:
            url = image["url"]

            # Change width to something absurd so we don't get a downscaled image
            # Idk if there is a better way to do it
            widthVal = url.split('/')[-2].split('=')[1]
            url = url.replace(f"width={widthVal}", "width=10000")

            # Checks if the extension is valid, and if it isn't set it to be saved as .jfif
            # So far I've only encountered those extensions, but I didn't check if they allow stuff like .webms   
            validExt = False
            validExtensions = ['.png', '.jpg',
                                '.jpeg', '.jfif', '.webp', '.avif', '.gif']
            for x in validExtensions:
                if url.endswith(x):
                    validExt = True
                    break

            # Clears and decodes the url before setting filename so it isn't full of things like $20 etc
            fileName = urllib.parse.unquote(url.split('/')[-1])
            not_allowed_chars = ['<', '>', ':',
                                    '"', '/', '\\', '|', '?', '*']
            fileName = ''.join(
                c for c in fileName if c not in not_allowed_chars)
            # Valid extension is only applied after everything is cleaned up, just to avoid any problems
            if not validExt:
                fileName += ".jfif"
            filePath = os.path.join(previewsPath, fileName)

            # Checks for duplicated imgs
            # This is a hotfix for files that previously had no extension in the url
            # (and were then download as jfif) to not be downloaded again as jpegs.
            # Since this might have happened with other files too I'm testing for every known extension
            fileExists = False
            if os.path.exists(filePath):
                    fileExists = True
                    fileSize = getFileSize(filePath)
            else:
                for extension in validExtensions:
                    oldPath = os.path.join(previewsPath, f"{fileName.split('.')[0]}{extension}")
                    if os.path.exists(oldPath):
                        fileExists = True
                        fileSize = getFileSize(oldPath)
                        break

            if fileExists:
                if (skip_duplicates and fileSize > 0):
                    continue
                elif fileSize <= 0 and redownload_corrupted:
                    print("Redownloading file because the existing one is corrupted.")
                elif fileSize > 0:
                    print("Renaming file because a file with the same name already exists.")
                    filePath = os.path.join(
                        previewsPath, f"{getCurrentTime()} - {fileName}")

            # Finally saves the image
            print(f"Model: {modelName}\nDownloading {url}")
            r = requests.get(url, stream=True)
            total_size_in_bytes= int(r.headers.get('content-length', 0))
            block_size = 1024 #1 Kibibyte
            progress_bar = tqdm.tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True)
            with open(filePath, 'wb') as f:
                for data in r.iter_content(block_size):
                    progress_bar.update(len(data))
                    f.write(data)

            progress_bar.close()


cwd = get_working_dir()
os.chdir(cwd)

# Basic config
models_folder = "models" # This doesn't work with full paths. It will just change the folder name.
civitai_token = None # If you want to increase your rate limits on Civitai, get your API token (from account setings) and put it there as a string
# Please be careful if you are using it and plan to do a push request.

# Metadata Options
updated_metadata = True
backup_metadata = True

# Models Options
skip_duplicate_models = True
use_subfolder = False # This will save models (.safetensors, .ckpt etc) under a subfolder named "files"

# Image Options
skip_duplicate_images = True
redownload_corrupted = False # Most of times corrupted files don't exist on Civitai anymore, but the API still return them when you request the model's metadata


while True:
    url_or_id = input("Enter the model URL or ID (separate multiple models with a comma):\n")

    url_or_id_list = url_or_id.split(',')
    
    for item in url_or_id_list:
        if item.startswith(' '): item = item[1:] # removes space if necessary, assuming the user entered multiple models as "id1, id2" etc
        if item.startswith("http") or url_or_id.startswith("civitai.com"):
            model_id = extract_id(item)
            if model_id is None:
                print_error()
                break
        else:
            model_id = item

        metadata = get_metadata(model_id, civitai_token= civitai_token)
        if metadata is None:
            print_error()
            if type(metadata) == str: print(f"Operation failed with code {metadata} for {item}")
            continue

        write_json(metadata= metadata, updated_metadata= updated_metadata, backup_metadata= backup_metadata, models_folder= models_folder)

        download_models(metadata= metadata, skip_duplicates= skip_duplicate_models, models_folder= models_folder, use_subfolder= use_subfolder)
        
        download_imgs(metadata= metadata, skip_duplicates= skip_duplicate_images, redownload_corrupted= redownload_corrupted, models_folder= models_folder)
