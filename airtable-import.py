"""
    Notes!
    
"""


import re, os.path, subprocess, time
import json, requests

debug = True
sendairtabletestdata = False

with open('C:\\airtabletest\\api_key.txt', 'r') as key:     # location of .txt file containing API token
    api_key = key.read()

with open('C:\\airtabletest\\url.txt', 'r') as url:         #   location of .txt file containing URL for the table in Airtable 
    url = url.read()                                        #   (found in api.airtable.com, not the same as the URL you see when browsing)

filefolder = 'C:\\airtabletest\\python-test\\'              # location of .pdf files
pdftotextlocation = 'C:\\airtabletest\\pdftotext'           # location of pdftotext.exe (obtained from xpdfreader.com commandline tools)

def checkfornewfiles():
#    try:
        for x in os.listdir(filefolder):
            if str(x)[-18:] != 'unknown format.txt' and str(x)[-3:] != 'txt': #   if filename doesn't contain 'unknown format.txt'
                                                                              #   and doesn't contain 'txt' at the end, then:
                subprocess.run([pdftotextlocation, '-nopgbrk', filefolder+str(x)]) # convert pdf to text
                filepath = filefolder+str(x)[:-4]           # create string of filepath to .txt file
                filetype = "None"
                print(filepath)
                while os.path.exists(filepath+".txt") != True:
                    time.sleep(.5)
                    print("Waiting for file creation")

                with open(filepath+'.txt', 'r+') as c:
                    n = c.read()
                line1 = n.split('\n', 1)[0]                 # first line of .txt file
                line2 = n.split('\n', 2)[1]                 # second line of .txt file
                if line1.startswith("Welcome to Volvo"):
                    filetype = "Volvo"
                elif line2.startswith("GSO:"):
                    filetype = "Mack"
                else:
                    print("Unknown format")
                    filetype = "None"
                    x = 20
                    while x > 0:
                        try:
                            os.rename(filepath+".txt", filepath+" unknown format.txt")  # rename file if not matched
                            break
                        except PermissionError:
                            time.sleep(3)
                            print("Permission error. Trying {x} more time(s)") 
                            x -= 1

                if filetype != "None":
                    print(filetype)
                    n = n.replace('\n', ' ')                # replace \n in file for easier RegEx processing (simplification)
                    if debug == True:
                        writefile(n, filepath)            
                    dataimport(n, filetype)
                    os.remove(filepath+'.txt')               

                print(x)
 #   except:
 #       print("something went wrong")


def writefile(n, filepath):                                 # write file for debugging
    a = open(filepath+' (debug).txt', 'w')
    a.write(n)
    a.close()

def dataimport(file, filetype):                             #   takes the file and processes it to take out the relevant information
    time.sleep(1)                                           #   according to which vendor it came from, then returns a list of dictionaries
    print(f"Importing {filetype} info")                     #   to be uploaded to Airtable

    content = []                                            # list of dictionaries, one dictionary per airtable row
    if filetype == "Mack":
        reg = re.compile(r'')
    elif filetype == "Volvo":
        reg = re.compile(r'')

    pattern = reg.search(file)

    return content
    

def posttoairtable(content):                                # uploads the data to Airtable
    headers = {
        "Authorization":str("Bearer "+api_key),
        "User-Agent":"Python Script",
        "Content-Type":"application/json"
    }
    x = requests.post(url,data=None,json=content,headers=headers)
    print("Post response: ",x.json())
    print("\n Post HTTP code:", x)

if debug == True and sendairtabletestdata == False:
    testdata={
        "records": [
            {
                "fields": {
                    "Name":"TULtest",
                    "Status":"Does Not Exist"
                }
            },
            {
                "fields": {
                    "Name":"TULtest2",
                    "Status":"Does Not Exist"
                }
            }
        ]
    }
    posttoairtable(testdata)
else:
    checkfornewfiles()                      # main
