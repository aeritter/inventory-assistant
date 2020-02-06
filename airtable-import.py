"""
    Ideally, it should work with the files in memory without needing to create
    an edited.txt file. Needs work.
"""


import re, os.path, subprocess, time
import json, requests

with open('C:\\airtabletest\\api_key.txt', 'r') as key:
    api_key = key.read()

with open('C:\\airtabletest\\url.txt', 'r') as url:
    url = str(url.read())

filefolder = 'C:\\airtabletest\\python-test\\'              #location of .pdf files
pdftotextlocation = 'C:\\airtabletest\\pdftotext'           #location of pdftotext.exe (obtained from xpdfreader.com commandline tools)

def checkfolder():
#    try:
        for x in os.listdir(filefolder):
            if str(x)[-18:] != 'unknown format.txt' and str(x)[-3:] != 'txt': #if filename doesn't contain 'unknown format.txt' and doesn't contain 'txt' at the end, then:
                subprocess.run([pdftotextlocation, '-nopgbrk', filefolder+str(x)]) #convert pdf to text
                filepath = filefolder+str(x)[:-4]           #create string of filepath to .txt file
                print(filepath)
                time.sleep(5)

                n = open(filepath+'.txt', 'r+')
                line1 = str(n.readline())                   #first line of .txt file
                n.readline()                                #second line of .txt file
                line3 = str(n.readline())                   #third line of .txt file
                if line1.startswith("MACK"):
                    print("Mack")
                    replacenewlines(n, filepath)
                    mackimport(filepath+' edited.txt')
                    os.remove(filepath+'.txt')
                    os.remove(filepath+' edited.txt')
                elif line3.startswith("PAGE 1"):
                    print("Volvo")
                    replacenewlines(n, filepath)
                    volvoimport(filepath+' edited.txt')
                    os.remove(filepath+'.txt')
                    os.remove(filepath+' edited.txt')
                else:
                    print("Unknown format")
                    os.rename(filepath, filepath[:-4]+" unknown format.txt")  #rename file if not matched

                n.close()
                print(x)
 #   except:
 #       print("something went wrong")


def replacenewlines(n, filepath):                           #changes file formatting for RegEx use
    m = n.read().replace('\n', ' ')
    a = open(filepath+' edited.txt', 'w')
    a.write(m)
    a.close()

def mackimport(file):
    time.sleep(1)
    print("Importing Mack info")

    content = {} #dictionary

    return content

def volvoimport(file):
    time.sleep(1)
    print("Importing Volvo info")
    

def posttoairtable(content):
    headers = {
        "Authorization":str("Bearer "+api_key),
        "User-Agent":"Python Script",
        "Content-Type":"application/json",
        "X-API-VERSION":"0.1.0",
    }
    x = requests.post(url,data=None,json=content,headers=headers)
    print("Post response: ",x.json(),"\n Post HTTP code:", x)

testdata={
    "fields": {
        "Name":"TULtest"
    }
}
posttoairtable(testdata)
