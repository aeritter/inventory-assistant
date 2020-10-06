# Airtable Import
A program designed to manage the data flow between services (SQL, Airtable, etc) and pull data from PDFs. Files are available to build a Docker container.

### Setup
After downloading, edit the settings.ini file to match what you need. Specifically, change the `pdf_folder` variable to whichever folder you want it to watch for PDF files. The other variables listed directly below are currently set to use subfolders of `pdf_folder`, but these can be changed to other locations if you would like.

If the folder you want to use for PDFs exists on a network share, you may need to enter credentials to an account that has access to the folder.

The program expects there to be a `pdftotext.exe` executable inside of the Settings folder. You can download this from xpdfreader.com from their download section under "Xpdf command line tools". It is in the zip file.

### To Run:
The program can be run directly, so long as you have Python installed and install any dependencies by running this command from the command line: `pip install pywin32, requests, PyMuPDF`.
Otherwise, it can be run from Docker by running the following commands from within the program's folder:
```
docker image build -t airtable .

docker run --name airtable --rm airtable
```
The first line will build the docker container image from the files in the current working directory according to the instructions in the Dockerfile. It will name the image `airtable`.
The second line will run the container after it has been built. The running container will be named `airtable` and will be automatically removed if the container stops. If you need to stop the container manually (to make a change and re-build the image), run: `docker container stop airtable`


***
# Folder Structures
Program Folder:
```
Main folder       - Contains all of the program's files.
├── main.py                  - The main program. Holds input/output queues and the datastore.
├── Dockerfile               - File containing instructions for Docker to build the Docker image. (editable as text file)
├── README.md                - This README document.
├── requirements.txt         - Contains a list of the Python modules that must be installed for the main program to work. Docker will use this file to run `pip install` within the container image.
├── settings.ini             - Contains the settings for the program including folder locations, network share credentials, API URLs, etc.
└── inputs folder  - For input modules
    ├── inventoryObject.py   - Contains the inventory object class for storing data (pull this into your inputs, fill it out, then push it to the input queue).
    └── pdfProcessor.py      - The module that handles PDF processing.
```

PDF Folder:
```
PDF main folder   - Contains the following folders, is the place where PDFs will be placed. PDF name does not matter.
├── Debug            - Contains debug files (pdftotext and regexmatches .txt files) and Debug.txt (which tells you information about errors). You can place a PDF in this folder to have it generate debug files for that PDF, in order to see what the program is pulling from that file.
├── Documents        - Contains finished Invoice and Order PDFs. The names for these are automatically determined from their contents.
├── Original Docs    - Contains the original .pdf files that were placed in the parent folder after they have been processed.
└── Settings         - Contains adjustable settings.
    ├── pdftotext.exe                 - This is the file downloaded from xpdfreader.com. It is necessary for the text extraction -- I haven't found anything better for getting text that can be parsed easily with RegEx.
    └── pdfProcessingSettings.json    - The JSON-formatted text file containing the values needed to properly pull information from the PDFs and parse and prepare it for Airtable
            
```
***
# Program Structure

## main.py
This is the main script. When a file is placed in the PDF folder, the program runs its processes on it to pull out the relevant information for creating a record in Airtable or updating one. It then moves those .pdf files to either the Done folder or the Errored folder, depending on whether the upload to Airtable was successful.

## Modules
All new modules should be added to the Modules folder. Each module should contain a class that should be passed an Input queue and an Error queue, both of which have a property called "addToQueue()". The module may also be passed a multiprocessing pool in case you would like to run multiple processes simultaneously.

The Input queue will accept a list with an Inventory object in the first position and a string with the name of the input in the second position. The string is there to let the program know not to send new information from this inventory object out to an output with the same name. Example: `[invObj, "pdfProcessor"]`

The Error queue will accept a list with a string in the first position to describe the error, and a dictionary in the second position for extra information. Example: `["Could not write file", {"File name":filename, "New location":"C:/test/"}]`

### inventoryObject.py

This module contains the class that should be instantiated for each object you want to add to the datastore. It can also be instantiated with updates to an object. Whenever one of these is made and sent to the Input queue, it will go to the datastore and update an entry if an entry already exists or it will create a new entry.

### Input - pdfProcessor.py

This module watches a given folder for new PDF files. When one is placed there, it extracts the text and begins processing. It will create a Page object for each page and then use the information contained on each page to determine how the file needs to be split (if it needs it at all). It will then compile all pages that relate to each other and create a Document object. 

Once it has a document object, it will process the document's text with RegEx to pull out all necessary info and then populate an inventory object with this data. After an inventory object has been made, it is sent to the Input queue.



### pdfProcessingSettings.json
This file lies in the Settings folder. It contains the information necessary to pull data out of PDF files.

It contains a few different keys:
* fileTypes
* ProcessingOrder
* SearchLists
* MatchLists
* ReplaceLists
* ignoreLists

Each of these serve different purposes.

**fileTypes:** This one has the information on each different type of document that will be processed. Within each filetype are 3 different keys: "Guide", "Defaults", and "Search". 

* **Guide**
The Guide tells the program what line to search and what to search for in order to determine if the document is a match for this file type. If it is a match, it will process the document according to the instructions left under this file type's "Search" parameter.
The value for "Guide" will be a list, where the first entry is a number used to tell the program which line to search. All entries after the line should be strings and if any of those strings are found in that line, the program will process the file according to that file type.

* **Defaults**
This key should contain a dictionary. Any key/value pairs in here are returned automatically as an input to the program. So if a certain document should always have certain attributes when entered into the datastore, you can place them here.

* **Search**
This tells the program how to parse the PDF after it has been converted to text. Details below.

**ProcessingOrder:** This one contains a list of strings, where a matching string should already exist in the "fileTypes" dictionary. The order of strings in this list will determine the order in which the program tests each document for a fileType match. 

**Lists:** These contain information to be used in the Search key. They exist to reduce repetition and consolidate some processing information.

#### Search
This parameter under each file type will tell the program how to parse the text and gather data from it. It should contain a list of dictionaries (ex. `"Search":[{},{},{}]`) with each dictionary containing different search parameters. The program processes each "Search" parameter recursively, meaning you can search in a variety of ways. For example:

* It can search for a given string (defined by the Regex parameter) and return the result.
* It can search for a given string and then search again within that string, then return that result.
* It can search for a pattern and if any of the results are a match a specific string, it can 

Here are the available keys and what they do:

* Regex
  * This should contain a string with your Python-formatted regular expression that will be used to find the string you are looking for.
  * Due to the way this is imported into the program, **double-up on your backslashes**.
  * Your regular expression should contain a group. The text found in the group is what will be processed/returned.
* Category
  * This should contain a string that is returned to the program along with the result of the RegEx search.
  * This is the "name" of your result. So if I give this a value of `"Color"` and the result of the RegEx search is `Blue` then the program will enter this into the datastore for this document: `"Color":"Blue"`
* Multiline (optional)
  * If this exists and has a value of 1 (not a string), the program will treat the RegEx string as a search that finds multiple results (the re.findall() function in Python).
  * If this exists and has a value of 1, the program expects there to also be a "Match" key in the dictionary as well.
* Match (optional, requires Multiline)
  * This will expect your regular expression to contain two (2) groups. The first one will be the text to match and the second one will be the text that is returned or processed further.
  * This should contain a dictionary with multiple keys. Each key is the text that you would expect to come from group 1 of the RegEx result. If there is a match, the program will search group 2 of the RegEx result according to whatever you have set as the value for the key (so just like your initial Search parameter where it contains a list of dictionaries and each dictionary contains processing data).

For both the `"Regex"` and the `"Match"` key, you can use a string instead of the expected list/dictionary. If you do so, the program will search for that string in either your `"SearchLists"` or `"MatchLists"` respectively. If it finds a child there with the same string, it will use the contents of that key as your search parameters instead. This should be used any time you would otherwise repeat yourself. If changes are needed to your settings, this gives you a single point of contact for those changes and will reduce the size of the settings file.


For an example, take a look at `pdfProcessingSettings.json` in the main folder.


### Airtable
Airtable receives data in this format:
```
{
  "records": [
    {
      "id": "recIDplacedhere",
      "fields": {
        "Stock": "41991",
        "Year": "2020",
        "Make": "Mack",
        "Model": "LR613"
        }
    }]
} 
```

"records" contains a list of records to create/update. A record is an individual row.

"id" refers to the row ID. This is only present when updating and is obtained from Airtable's API when searching for records.

"fields" contains a list of column names and the entry that goes in that column for that record.




# Debugging
