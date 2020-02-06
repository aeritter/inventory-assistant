"""
    Ideally, it should work with the files in memory without needing to create
    an edited.txt file. Needs work.
"""


import re, os.path, subprocess, time
import json, requests

with open('C:\\airtabletest\\api_key.txt', 'r') as key:     # location of .txt file containing API token
    api_key = key.read()

with open('C:\\airtabletest\\url.txt', 'r') as url:         #   location of .txt file containing URL for the table in Airtable 
    url = str(url.read())                                   #   (found in api.airtable.com, not the same as the URL you see when browsing)

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
                time.sleep(5)

                n = open(filepath+'.txt', 'r+')
                line1 = str(n.readline())                   # first line of .txt file
                n.readline()                                # second line of .txt file
                line3 = str(n.readline())                   # third line of .txt file
                if line1.startswith("MACK"):
                    filetype = "Mack"
                elif line3.startswith("PAGE 1"):
                    filetype = "Volvo"
                else:
                    print("Unknown format")
                    filetype = "None"
                    os.rename(filepath, filepath[:-4]+" unknown format.txt")  # rename file if not matched

                if filetype != "None":
                    print(filetype)
                    replacenewlines(n, filepath)
                    dataimport(filepath+' edited.txt', filetype)
                    os.remove(filepath+'.txt')
                    os.remove(filepath+' edited.txt')                    

                n.close()
                print(x)
 #   except:
 #       print("something went wrong")


def replacenewlines(n, filepath):                           # changes file formatting for RegEx use
    m = n.read().replace('\n', ' ')
    a = open(filepath+' edited.txt', 'w')
    a.write(m)
    a.close()

def dataimport(file, filetype):                             #   takes the file and processes it to take out the relevant information
    time.sleep(1)                                           #   according to which vendor it came from, then returns a list of dictionaries
    print("Importing %s info", filetype)                    #   to be uploaded to Airtable

    content = []                                            # list of dictionaries, one dictionary per airtable row

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
